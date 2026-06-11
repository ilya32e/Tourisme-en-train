"""
Recommandateur de destinations en train SANS VOITURE.
EFREI Learning XP « Tourisme en train » — utilisateur : grand public / touristes.

Pour chaque destination, on croise :
  • le trajet SNCF (durée + CO₂)            -> /journeys
  • la météo à l'arrivée                    -> Open-Meteo (sans clé)
  • les ACTIVITÉS accessibles à pied        -> OpenStreetMap/Overpass (poi.py)
puis on calcule un SCORE COMPOSITE personnalisé (centres d'intérêt + rayon de
marche) et on classe les destinations, avec la liste des activités à pied.

Réutilise le moteur de sncf_demo.py (auth, cache, MODE DÉGRADÉ).

Exemples :
  python escapades.py
  python escapades.py "Lyon Part-Dieu" --interets plage,culture --marche 1500 --max 180
"""

import argparse
import math
import os
import re
import statistics
import sys
import time
import urllib.parse
from pathlib import Path

# permet de lancer ce fichier en script (python src/escapade/recommender.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from escapade import ml
from escapade.paths import load_env
from escapade.sncf import api_get, http_get_json, resolve_stop_area, WMO
from escapade.sources import ademe, events, poi_datatourisme, poi_osm

load_env()

# Source POI : DATAtourisme (mieux typé) si la clé est présente, sinon OSM/Overpass
POI = poi_datatourisme if os.environ.get("DATATOURISME_KEY") else poi_osm

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_ORIGIN = "Paris Gare de Lyon"
DESTINATIONS = [
    "Lyon Part-Dieu", "Bordeaux Saint-Jean", "Marseille Saint-Charles",
    "Nantes", "Strasbourg", "Rennes", "Lille Europe", "Toulouse Matabiau",
    "Montpellier Saint-Roch", "Nice", "Avignon Centre", "Annecy",
    "Biarritz", "La Rochelle", "Dijon",
]

# Indice d'ensoleillement (0 = pourri, 1 = grand soleil) par code météo WMO.
# Sert de variable numérique pour le score ; défaut prudent à 0.2.
SUN = {
    0: 1.0, 1: 0.9, 2: 0.65, 3: 0.4,
    45: 0.3, 48: 0.3, 51: 0.3, 53: 0.25, 55: 0.2, 56: 0.2, 57: 0.15,
    61: 0.25, 63: 0.15, 65: 0.1, 66: 0.1, 67: 0.05,
    71: 0.2, 73: 0.15, 75: 0.1, 77: 0.15,
    80: 0.3, 81: 0.2, 82: 0.1, 85: 0.15, 86: 0.1,
    95: 0.05, 96: 0.0, 99: 0.0,
}

# Pondérations du score — JUSTIFIÉES (guide 06, attendu en soutenance) :
#   activités = cœur du « sans voiture » (qu'y a-t-il à faire à pied ?) -> poids fort
#   soleil    = une sortie se profite par beau temps
#   calme     = éviter la foule (fréquentation de la gare, inversée)
#   durée     = rester accessible (escapade, pas expédition)
#   CO₂       = cohérence avec la promesse « train = bas carbone »
POIDS = {"activites": 0.30, "soleil": 0.25, "calme": 0.20, "duree": 0.15, "co2": 0.10}


# --------------------------------------------------------------------------- #
# Collecte des données par destination (API SNCF + Open-Meteo)
# --------------------------------------------------------------------------- #
def slug(name):
    # nom complet normalisé : évite que deux gares partageant le 1er mot
    # (« Paris … ») se partagent la même clé de cache.
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


# Facteur voiture thermique (par voyageur) — moyenne du dataset SNCF/ADEME
# emission-co2-perimetre-complet. Sert à estimer le CO₂ économisé vs voiture.
CAR_CO2_G_PER_KM = 89


def _haversine_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    dla, dlo = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = (math.sin(dla / 2) ** 2
         + math.cos(math.radians(la1)) * math.cos(math.radians(la2)) * math.sin(dlo / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def co2_saved_kg(origin_coord, dest_coord, train_co2_g, cache_name=None):
    """CO₂ économisé vs voiture (kg). Voiture : valeur ADEME officielle si clé
    présente, sinon estimation (facteur dataset SNCF ~89 g/km)."""
    if None in origin_coord or None in dest_coord:
        return None
    road_km = _haversine_km(origin_coord, dest_coord) * 1.3  # détour route ≈ +30 %
    car_kg = ademe.get_car_kg(road_km, cache_name)
    if car_kg is None:
        car_kg = road_km * CAR_CO2_G_PER_KM / 1000
    return max(0.0, car_kg - train_co2_g / 1000)


def journey_stats(from_id, to_id, cache_name):
    data, _ = api_get(
        "/journeys",
        {"from": from_id, "to": to_id,
         "disable_geojson": "true", "data_freshness": "realtime"},
        cache_name,
    )
    journeys = data.get("journeys", [])
    if not journeys:
        return None, None
    # l'API ne renvoie pas toujours le plus rapide en premier -> on le choisit
    best = min(journeys, key=lambda j: j.get("duration", 10**9))
    minutes = best.get("duration", 0) // 60
    co2 = best.get("co2_emission", {}).get("value")
    return minutes, co2


def weather_at(coord, cache_name):
    lat, lon = coord
    if lat is None or lon is None:
        return None, None, "coordonnées inconnues"
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=weather_code,temperature_2m_max&timezone=Europe%2FParis&forecast_days=1"
    )
    data, _ = http_get_json(url, cache_name)
    daily = data.get("daily", {})
    code = daily.get("weather_code", [None])[0]
    temp = daily.get("temperature_2m_max", [None])[0]
    label = WMO.get(code, ("Météo inconnue", False))[0]
    return SUN.get(code, 0.2), temp, label


def frequentation(uic, cache_name):
    """Fréquentation annuelle de la gare (voyageurs 2024) -> proxy d'affluence."""
    if not uic:
        return None
    url = (
        "https://ressources.data.sncf.com/api/explore/v2.1/catalog/"
        "datasets/frequentation-gares/records?"
        + urllib.parse.urlencode({
            "where": f'code_uic_complet="{uic}"',
            "select": "total_voyageurs_2024",
            "limit": 1,
        })
    )
    try:
        data, _ = http_get_json(url, cache_name)
    except Exception:
        return None
    results = data.get("results", [])
    return results[0].get("total_voyageurs_2024") if results else None


def collect(origin, interests, radius):
    print(f"→ Origine : {origin}  ·  intérêts : {', '.join(interests)}  ·  marche : {radius} m")
    origin_id, origin_name, origin_coord, _ = resolve_stop_area(
        origin, f"place_{slug(origin)}"
    )

    rows = []
    for dest in DESTINATIONS:
        if slug(dest) == slug(origin):
            continue  # ne pas se proposer sa propre gare de départ
        s = slug(dest)
        dest_id, dest_name, coord, _ = resolve_stop_area(dest, f"place_{s}")
        # clé incluant l'origine : un trajet dépend du couple (départ, arrivée)
        minutes, co2 = journey_stats(origin_id, dest_id, f"journey_{slug(origin)}_{s}")
        soleil, temp, meteo = weather_at(coord, f"weather_{s}")
        if minutes is None or co2 is None or soleil is None:
            print(f"   (ignoré : données incomplètes pour {dest_name})")
            continue

        # Activités accessibles à pied (POIs OSM dans le rayon de marche)
        lat, lon = coord
        pois, poi_src = POI.get_pois(lat, lon, radius=radius, cache_name=f"{s}_{radius}")
        counts, names = pois["counts"], pois["names"]
        if poi_src == "API":
            time.sleep(1)  # politesse Overpass (~1 req/s) ; ignoré si servi du cache
        activites_raw = sum(counts.get(c, 0) for c in interests)

        # Affluence : fréquentation annuelle de la gare (UIC dérivé du stop_area)
        uic = dest_id.split(":")[-1] if dest_id else None
        freq = frequentation(uic, f"freq_{s}")

        # Événements à venir dans la ville (OpenAgenda) — info, hors score
        evts = events.get_events(dest_name, f"events_{s}")

        rows.append({
            "ville": dest_name, "minutes": minutes, "co2": co2,
            "soleil": soleil, "temp": temp, "meteo": meteo, "coord": coord,
            "activites_raw": activites_raw, "poi_counts": counts, "poi_names": names,
            "frequentation": freq,
            # ML : affinité content-based (similarité cosinus profil POI ↔ intérêts)
            "affinite": ml.affinity(counts, interests),
            # CO₂ économisé vs voiture (dataset emission-co2-perimetre-complet)
            "co2_economie": co2_saved_kg(origin_coord, coord, co2, f"{slug(origin)}_{s}"),
            "events": evts,
        })
        foule = f", {freq // 1000}k voy./an" if freq else ""
        print(f"   ✓ {dest_name}  ({activites_raw} activités à pied{foule})")
    return origin_name, origin_coord, rows


# --------------------------------------------------------------------------- #
# Scoring composite — méthode guide 06 (normalisation min-max + pondération)
# --------------------------------------------------------------------------- #
def minmax(values):
    lo, hi = min(values), max(values)
    span = hi - lo
    return [(v - lo) / span if span else 0.5 for v in values]


def score_rows(rows):
    soleil_n = minmax([r["soleil"] for r in rows])
    # « activités » = affinité ML (cosinus profil POI ↔ intérêts), déjà dans [0,1]
    act_n = [r["affinite"] for r in rows]
    # durée et CO₂ : plus c'est bas, mieux c'est -> on inverse (1 - x)
    duree_n = [1 - x for x in minmax([r["minutes"] for r in rows])]
    co2_n = [1 - x for x in minmax([r["co2"] for r in rows])]

    # Calme = fréquentation inversée (peu de monde = mieux). Valeurs manquantes
    # remplacées par la médiane (neutre) pour ne pas fausser la normalisation.
    freqs = [r["frequentation"] for r in rows]
    known = [f for f in freqs if f is not None]
    fill = statistics.median(known) if known else 0
    freq_filled = [f if f is not None else fill for f in freqs]
    calme_n = [1 - x for x in minmax(freq_filled)]

    for r, sn, an, kn, dn, cn in zip(rows, soleil_n, act_n, calme_n, duree_n, co2_n):
        r["n_soleil"], r["n_activites"], r["n_calme"] = sn, an, kn
        r["n_duree"], r["n_co2"] = dn, cn
        r["score"] = (
            POIDS["activites"] * an + POIDS["soleil"] * sn + POIDS["calme"] * kn
            + POIDS["duree"] * dn + POIDS["co2"] * cn
        )

    # ML 2 : profils de villes (k-means sur le mix d'activités). Chaque ville
    # reçoit son profil + ses « villes similaires » (même cluster, triées par
    # similarité cosinus) → alternatives au même ADN que la recommandation.
    labels, noms = ml.city_profiles([r["poi_counts"] for r in rows])
    for i, (r, lab) in enumerate(zip(rows, labels)):
        r["profil"] = noms[lab]
        peers = [
            (rows[j]["ville"].split("(")[0].strip(),
             ml.similarity(r["poi_counts"], rows[j]["poi_counts"]))
            for j in range(len(rows)) if j != i and labels[j] == lab
        ]
        r["similaires"] = sorted(peers, key=lambda p: p[1], reverse=True)[:3]

    return sorted(rows, key=lambda r: r["score"], reverse=True)


# --------------------------------------------------------------------------- #
def emoji_for(label):
    low = label.lower()
    if "orage" in low:
        return "⛈️"
    if "neige" in low:
        return "🌨️"
    if "pluie" in low or "averse" in low or "bruine" in low:
        return "🌧️"
    if "brouillard" in low:
        return "🌫️"
    if "couvert" in low:
        return "☁️"
    if "nuageux" in low:
        return "⛅"
    return "☀️"


# --------------------------------------------------------------------------- #
# Rapport visuel HTML (cartes + barres de score + carte Leaflet/OpenStreetMap)
# --------------------------------------------------------------------------- #
def write_html(origin_name, origin_coord, classement, path="escapade_report.html"):
    import html
    import json as _json
    from datetime import date

    cards, points = [], []
    for rank, r in enumerate(classement, 1):
        h, m = divmod(r["minutes"], 60)
        ville = r["ville"].split("(")[0].strip()
        temp = f"{r['temp']:.0f}°C" if r["temp"] is not None else "—"
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"{rank}.")
        foule = f"{r['frequentation'] // 1000}k voy./an" if r.get("frequentation") else "—"
        eco = f" &nbsp;|&nbsp; 🌍 −{r['co2_economie']:.0f} kg vs voiture" if r.get("co2_economie") else ""
        evt = f" &nbsp;|&nbsp; 🎉 {r['events']} évén." if r.get("events") else ""
        prof = (f" &nbsp;|&nbsp; {html.escape(r['profil'])}"
                if r.get("profil") and r["profil"] != "—" else "")
        cards.append(f"""
      <div class="card">
        <div class="rank">{medal}</div>
        <div class="body">
          <div class="city">{html.escape(ville)} <span class="wx">{emoji_for(r['meteo'])}</span></div>
          <div class="meta">🎯 {r['affinite']:.0%} d'affinité &nbsp;|&nbsp; 🚶 {r['activites_raw']} activités &nbsp;|&nbsp; 🚆 {h}h{m:02d}{eco}{evt}{prof}</div>
          <div class="bar"><span style="width:{r['score']*100:.0f}%"></span></div>
          <div class="sub">score {r['score']:.2f} — affinité {r['n_activites']:.2f} · soleil {r['n_soleil']:.2f} · calme {r['n_calme']:.2f} · durée {r['n_duree']:.2f} · CO₂ {r['n_co2']:.2f} &nbsp;·&nbsp; foule {foule}</div>
        </div>
      </div>""")
        lat, lon = r["coord"]
        if lat is not None and lon is not None:
            points.append({
                "lat": lat, "lon": lon, "rank": rank, "ville": ville,
                "meteo": r["meteo"], "emoji": emoji_for(r["meteo"]),
                "duree": f"{h}h{m:02d}", "score": round(r["score"], 2),
                "affinite": f"{r['affinite']:.0%}",
            })

    olat, olon = origin_coord
    origin_js = (
        _json.dumps({"lat": olat, "lon": olon, "name": origin_name.split("(")[0].strip()})
        if olat is not None else "null"
    )

    doc = f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Escapades en train depuis {html.escape(origin_name)}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --accent:#38bdf8; --text:#e2e8f0; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font-family:system-ui,Segoe UI,sans-serif; background:var(--bg); color:var(--text); }}
  header {{ padding:24px; text-align:center; }}
  header h1 {{ margin:0 0 4px; font-size:1.5rem; }}
  header p {{ margin:0; color:#94a3b8; }}
  .wrap {{ max-width:1100px; margin:0 auto; padding:0 16px 40px; display:grid; grid-template-columns:1fr 1fr; gap:20px; }}
  #map {{ height:520px; border-radius:14px; }}
  .cards {{ display:flex; flex-direction:column; gap:12px; }}
  .card {{ display:flex; gap:14px; background:var(--card); border-radius:14px; padding:14px 16px; align-items:center; }}
  .rank {{ font-size:1.6rem; min-width:34px; text-align:center; }}
  .city {{ font-weight:600; font-size:1.1rem; }}
  .wx {{ font-size:1.2rem; }}
  .meta {{ color:#94a3b8; font-size:.85rem; margin:3px 0 8px; }}
  .bar {{ height:8px; background:#334155; border-radius:6px; overflow:hidden; }}
  .bar span {{ display:block; height:100%; background:linear-gradient(90deg,#38bdf8,#22c55e); }}
  .sub {{ color:#64748b; font-size:.72rem; margin-top:6px; }}
  footer {{ text-align:center; color:#64748b; font-size:.8rem; padding:16px; }}
  @media (max-width:820px) {{ .wrap {{ grid-template-columns:1fr; }} #map {{ height:360px; }} }}
</style></head>
<body>
  <header>
    <h1>🚆☀️ Escapades en train depuis {html.escape(origin_name.split("(")[0].strip())}</h1>
    <p>Classées par affinité (ML) · météo · calme · durée · CO₂ — généré le {date.today():%d/%m/%Y}</p>
  </header>
  <div class="wrap">
    <div class="cards">{''.join(cards)}</div>
    <div id="map"></div>
  </div>
  <footer>Données : API SNCF (/journeys) + Open-Meteo · fond de carte © OpenStreetMap</footer>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
  const points = {_json.dumps(points, ensure_ascii=False)};
  const origin = {origin_js};
  const map = L.map('map');
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',
    {{ maxZoom: 12, attribution: '© OpenStreetMap' }}).addTo(map);
  const group = [];
  if (origin) {{
    const o = L.marker([origin.lat, origin.lon]).addTo(map)
      .bindPopup('<b>Départ : ' + origin.name + '</b>');
    group.push([origin.lat, origin.lon]);
  }}
  points.forEach(p => {{
    L.marker([p.lat, p.lon]).addTo(map)
      .bindPopup('<b>#' + p.rank + ' ' + p.ville + ' ' + p.emoji + '</b><br>' +
                 '🎯 ' + p.affinite + ' · 🚆 ' + p.duree + ' · score ' + p.score);
    group.push([p.lat, p.lon]);
  }});
  map.fitBounds(group, {{ padding: [40, 40] }});
</script>
</body></html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Top des escapades en train selon la météo à l'arrivée."
    )
    parser.add_argument(
        "origin", nargs="?", default=DEFAULT_ORIGIN,
        help=f'gare de départ (défaut : "{DEFAULT_ORIGIN}")',
    )
    parser.add_argument(
        "--interets", default=",".join(POI.CATEGORIES),
        metavar="LISTE",
        help="centres d'intérêt séparés par des virgules "
             f"(parmi : {', '.join(POI.CATEGORIES)})",
    )
    parser.add_argument(
        "--marche", type=int, default=1000, metavar="M",
        help="rayon de marche autour de la gare, en mètres (défaut 1000)",
    )
    parser.add_argument(
        "--max", type=int, default=None, metavar="MIN",
        help="durée de trajet maximale, en minutes (ex. --max 180 pour ≤ 3 h)",
    )
    parser.add_argument(
        "--top", type=int, default=None, metavar="N",
        help="n'afficher que les N meilleures destinations",
    )
    parser.add_argument(
        "--html", action="store_true",
        help="générer un rapport visuel HTML (carte + cartes) et l'ouvrir",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    interests = [i.strip() for i in args.interets.split(",") if i.strip() in POI.CATEGORIES]
    if not interests:
        raise SystemExit(f"Intérêts invalides. Choix : {', '.join(POI.CATEGORIES)}")

    origin_name, origin_coord, rows = collect(args.origin, interests, args.marche)
    if not rows:
        raise SystemExit("Aucune destination exploitable.")

    # Filtre durée max (amélioration : escapade « ≤ X h »)
    if args.max is not None:
        kept = [r for r in rows if r["minutes"] <= args.max]
        écartées = len(rows) - len(kept)
        if écartées:
            print(f"   ({écartées} destination(s) écartée(s) : trajet > {args.max} min)")
        rows = kept
        if not rows:
            raise SystemExit(f"Aucune destination à ≤ {args.max} min depuis {args.origin}.")

    classement = score_rows(rows)
    if args.top is not None:
        classement = classement[: args.top]

    print("\n" + "=" * 70)
    print(f"  DESTINATIONS SANS VOITURE DEPUIS {args.origin.upper()}")
    print("=" * 70)
    print(f"  {'#':<2} {'Destination':<24} {'Durée':>6} {'Activ.':>6} {'Affin.':>6} {'Score':>6}")
    print("  " + "-" * 64)
    for rank, r in enumerate(classement, 1):
        h, m = divmod(r["minutes"], 60)
        duree = f"{h}h{m:02d}"
        ville = r["ville"].split("(")[0].strip()
        print(
            f"  {rank:<2} {ville[:24]:<24} {duree:>6} "
            f"{r['activites_raw']:>6} {r['affinite']:>6.2f} {r['score']:>6.2f}"
        )

    best = classement[0]
    ville = best["ville"].split("(")[0].strip()
    print("\n→ Recommandation")
    eco = f" · ~{best['co2_economie']:.0f} kg CO₂ économisés vs voiture" if best.get("co2_economie") else ""
    ev = f" · {best['events']} événements à venir" if best.get("events") else ""
    print(
        f"   🚆 Cap sur {ville} : {best['meteo'].lower()}, "
        f"{best['minutes'] // 60}h{best['minutes'] % 60:02d} de train, "
        f"{best['co2']:.0f} g CO₂ — et tout à pied ! (affinité {best['affinite']:.0%}{eco}{ev})"
    )
    # Profil de ville appris (k-means) + alternatives au même ADN
    if best.get("profil") and best["profil"] != "—":
        sims = " · ".join(f"{v} ({s:.2f})" for v, s in best.get("similaires", []))
        print(f"   Profil de ville : {best['profil']}"
              + (f"  —  même profil : {sims}" if sims else ""))

    # Les activités à pied du gagnant, par centre d'intérêt
    print("   Activités à pied :")
    for cat in interests:
        n = best["poi_counts"].get(cat, 0)
        if n:
            ex = ", ".join(best["poi_names"].get(cat, [])[:3])
            print(f"     • {cat:<11} {n:>3}" + (f"  ({ex})" if ex else ""))

    print(
        f"   détail → affinité {best['n_activites']:.2f} · soleil {best['n_soleil']:.2f} · "
        f"calme {best['n_calme']:.2f} · durée {best['n_duree']:.2f} · CO₂ {best['n_co2']:.2f}"
    )

    if args.html:
        import webbrowser
        from pathlib import Path

        path = write_html(origin_name, origin_coord, classement)
        full = Path(path).resolve()
        print(f"\n→ Rapport visuel : {full}")
        webbrowser.open(full.as_uri())


if __name__ == "__main__":
    main()
