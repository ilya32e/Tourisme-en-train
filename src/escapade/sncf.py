"""
Démo API SNCF — Paris -> Lyon
EFREI Learning XP « Tourisme en train »

Ce script suit le parcours des guides 02 et 04 du starter kit :
  1. charge la clé depuis .env  (jamais de clé en dur — guide 03)
  2. résout l'identifiant des gares via /places  (jamais un id copié ailleurs — guide 02)
  3. calcule un itinéraire via /journeys
  4. MODE DÉGRADÉ : si l'API ne répond pas, on rejoue la dernière réponse mise en cache (guide 04)

Aucune dépendance à installer : uniquement la bibliothèque standard.
Lancement :  python sncf_demo.py
"""

import os
import sys
import json
import base64
import urllib.parse
import urllib.request
import urllib.error
from datetime import date

from escapade.paths import CACHE, load_env

# Console Windows : forcer l'UTF-8 pour afficher → ⚠️ ₂ sans planter (cp1252)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://api.sncf.com/v1/coverage/sncf"

load_env()
API_KEY = os.environ.get("SNCF_API_KEY")

# Compteur de quota journalier (5000/j) : alerte à ~3000 pour basculer sur le cache
QUOTA_FILE = CACHE / ".quota.json"
QUOTA_WARN = 3000


def _bump_quota():
    """Incrémente le compteur d'appels SNCF du jour ; alerte au seuil conseillé."""
    today = date.today().isoformat()
    try:
        d = json.loads(QUOTA_FILE.read_text(encoding="utf-8")) if QUOTA_FILE.exists() else {}
    except Exception:
        d = {}
    if d.get("date") != today:
        d = {"date": today, "count": 0}
    d["count"] += 1
    if d["count"] == QUOTA_WARN:
        print(f"   ⚠️  ~{QUOTA_WARN} requêtes SNCF aujourd'hui (sur 5000) "
              "→ basculez sur le cache (RECO_CACHE_FIRST=1 / mode dégradé).")
    try:
        CACHE.mkdir(exist_ok=True)
        QUOTA_FILE.write_text(json.dumps(d), encoding="utf-8")
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# 2. Appel API authentifié, avec cache + repli automatique (mode dégradé)
# --------------------------------------------------------------------------- #
def api_get(path, params=None, cache_name=None):
    """Retourne (data, source) où source vaut 'API' ou 'CACHE'."""
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    cache_file = CACHE / f"{cache_name}.json" if cache_name else None

    # Mode cache-first (interface) : si le cache existe, on le sert sans réseau.
    if cache_file and cache_file.exists() and os.environ.get("RECO_CACHE_FIRST") == "1":
        return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"

    try:
        if not API_KEY:
            raise RuntimeError("SNCF_API_KEY absente du .env")

        # HTTP Basic : clé = username, mot de passe vide  -> "cle:" en base64
        token = base64.b64encode(f"{API_KEY}:".encode()).decode()
        request = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})

        with urllib.request.urlopen(request, timeout=10) as response:
            data = json.load(response)
        _bump_quota()  # un vrai appel réseau a été consommé

        # on garde une copie pour le mode dégradé
        if cache_file:
            CACHE.mkdir(exist_ok=True)
            cache_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return data, "API"

    except urllib.error.HTTPError as error:
        if error.code == 429:  # quota : NE PAS relancer tout de suite (backoff ≥ 30 s)
            print("   ⚠️  429 quota atteint : bascule cache. Attendre ≥ 30 s avant de réessayer.")
        elif error.code == 401:
            print("   ⚠️  401 : vérifier la clé, le « : » final et le header Authorization.")
        else:
            print(f"   ⚠️  API indisponible (HTTP {error.code}). Mode dégradé.")
        if cache_file and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
        raise SystemExit(f"❌ Échec API et aucun cache pour « {cache_name} » : {error}")

    except Exception as error:  # réseau coupé, 5xx, clé absente...
        if cache_file and cache_file.exists():
            print(f"   ⚠️  API indisponible ({error}). Mode dégradé : cache local.")
            return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
        raise SystemExit(f"❌ Échec API et aucun cache pour « {cache_name} » : {error}")


# --------------------------------------------------------------------------- #
# 3. Résoudre une gare -> son identifiant stop_area
# --------------------------------------------------------------------------- #
def resolve_stop_area(query, cache_name):
    data, source = api_get(
        "/places", {"q": query, "type[]": "stop_area"}, cache_name
    )
    places = data.get("places", [])
    if not places:
        raise SystemExit(f"❌ Aucun lieu trouvé pour « {query} »")
    # on privilégie un vrai stop_area
    chosen = next(
        (p for p in places if p.get("embedded_type") == "stop_area"), places[0]
    )
    coord = chosen.get("stop_area", {}).get("coord", {})
    lat = float(coord["lat"]) if coord.get("lat") else None
    lon = float(coord["lon"]) if coord.get("lon") else None
    return chosen["id"], chosen["name"], (lat, lon), source


# --------------------------------------------------------------------------- #
# 4. Calculer et résumer un itinéraire
# --------------------------------------------------------------------------- #
def show_journey(from_id, to_id, cache_name):
    data, source = api_get(
        "/journeys",
        {"from": from_id, "to": to_id,
         "disable_geojson": "true", "data_freshness": "realtime"},
        cache_name,
    )
    journeys = data.get("journeys", [])
    if not journeys:
        print("   Aucun itinéraire renvoyé.")
        return

    best = journeys[0]
    minutes = best.get("duration", 0) // 60
    co2 = best.get("co2_emission", {}).get("value")

    print(f"   Durée : {minutes // 60} h {minutes % 60:02d} min   [source : {source}]")
    if co2 is not None:
        print(f"   CO₂   : {co2:.0f} g")
    print("   Trajet :")
    for section in best.get("sections", []):
        if section.get("type") != "public_transport":
            continue
        info = section.get("display_informations", {})
        label = info.get("commercial_mode", "Train")
        number = info.get("headsign", "")
        dep = section["from"]["name"]
        arr = section["to"]["name"]
        print(f"     • {label} {number} : {dep} → {arr}")


# --------------------------------------------------------------------------- #
# 5. Prochains départs d'une gare
# --------------------------------------------------------------------------- #
def show_departures(stop_area_id, cache_name, limit=5):
    data, source = api_get(
        f"/stop_areas/{stop_area_id}/departures",
        {"count": limit, "data_freshness": "realtime"},
        cache_name,
    )
    departures = data.get("departures", [])
    if not departures:
        print("   Aucun départ à venir.")
        return

    print(f"   [source : {source}]")
    for dep in departures[:limit]:
        info = dep.get("display_informations", {})
        mode = info.get("commercial_mode", "Train")
        number = info.get("headsign", "")
        direction = info.get("direction", "")
        # format SNCF : "20260608T101500" -> "10:15"
        raw = dep.get("stop_date_time", {}).get("departure_date_time", "")
        heure = f"{raw[9:11]}:{raw[11:13]}" if len(raw) >= 13 else "??:??"
        print(f"     • {heure}  {mode} {number} → {direction}")


# --------------------------------------------------------------------------- #
# 6. Perturbations en cours sur le réseau
# --------------------------------------------------------------------------- #
def show_disruptions(cache_name, limit=5):
    data, source = api_get("/disruptions", {"count": limit}, cache_name)
    disruptions = data.get("disruptions", [])
    if not disruptions:
        print("   Aucune perturbation signalée. 🎉")
        return

    print(f"   [source : {source}]")
    for dis in disruptions[:limit]:
        severity = dis.get("severity", {}).get("name", "info")
        # le message peut contenir du HTML : on prend le 1er, brut
        messages = dis.get("messages", [])
        text = messages[0]["text"] if messages else "(pas de détail)"
        text = text.replace("\n", " ").strip()
        if len(text) > 120:
            text = text[:117] + "..."
        print(f"     • [{severity}] {text}")


# --------------------------------------------------------------------------- #
# 7. Météo à l'arrivée (Open-Meteo, sans clé) — 2e source de données
# --------------------------------------------------------------------------- #
# Codes météo WMO -> libellé + drapeau "beau temps" pour le score escapade
WMO = {
    0: ("Ciel dégagé", True), 1: ("Plutôt ensoleillé", True),
    2: ("Partiellement nuageux", True), 3: ("Couvert", False),
    45: ("Brouillard", False), 48: ("Brouillard givrant", False),
    51: ("Bruine légère", False), 53: ("Bruine", False), 55: ("Bruine dense", False),
    56: ("Bruine verglaçante", False), 57: ("Bruine verglaçante dense", False),
    61: ("Pluie faible", False), 63: ("Pluie", False), 65: ("Forte pluie", False),
    66: ("Pluie verglaçante", False), 67: ("Forte pluie verglaçante", False),
    71: ("Neige faible", False), 73: ("Neige", False), 75: ("Forte neige", False),
    77: ("Grains de neige", False),
    80: ("Averses faibles", False), 81: ("Averses", False), 82: ("Fortes averses", False),
    85: ("Averses de neige", False), 86: ("Fortes averses de neige", False),
    95: ("Orage", False), 96: ("Orage avec grêle", False), 99: ("Violent orage", False),
}


def http_get_json(url, cache_name):
    """GET JSON sans authentification, avec cache + mode dégradé (comme api_get)."""
    cache_file = CACHE / f"{cache_name}.json"
    if cache_file.exists() and os.environ.get("RECO_CACHE_FIRST") == "1":
        return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.load(response)
        CACHE.mkdir(exist_ok=True)
        cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return data, "API"
    except Exception as error:
        if cache_file.exists():
            print(f"   ⚠️  Open-Meteo indisponible ({error}). Mode dégradé : cache local.")
            return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
        raise SystemExit(f"❌ Échec Open-Meteo et aucun cache : {error}")


def show_weather(coord, cache_name):
    """Affiche la météo du jour à destination et retourne True si beau temps."""
    lat, lon = coord
    if lat is None or lon is None:
        print("   Coordonnées indisponibles, météo ignorée.")
        return None

    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        "&daily=weather_code,temperature_2m_max&timezone=Europe%2FParis&forecast_days=1"
    )
    data, source = http_get_json(url, cache_name)
    daily = data.get("daily", {})
    code = daily.get("weather_code", [None])[0]
    temp = daily.get("temperature_2m_max", [None])[0]

    label, beau = WMO.get(code, ("Météo inconnue", False))
    temp_txt = f"{temp:.0f}°C" if temp is not None else "?°C"
    print(f"   {label}, {temp_txt} max   [source : {source}]")
    return beau


# --------------------------------------------------------------------------- #
# Programme principal
# --------------------------------------------------------------------------- #
def main():
    print("→ Résolution des gares via /places")
    paris_id, paris_name, _, _ = resolve_stop_area("Paris Gare de Lyon", "place_paris")
    lyon_id, lyon_name, lyon_coord, _ = resolve_stop_area("Lyon Part-Dieu", "place_lyon")
    print(f"   {paris_name} = {paris_id}")
    print(f"   {lyon_name} = {lyon_id}\n")

    print(f"→ Itinéraire {paris_name} → {lyon_name}")
    show_journey(paris_id, lyon_id, "journey_paris_lyon")

    print(f"\n→ Prochains départs depuis {paris_name}")
    show_departures(paris_id, "departures_paris")

    print("\n→ Perturbations en cours sur le réseau")
    show_disruptions("disruptions")

    print(f"\n→ Météo à l'arrivée ({lyon_name})")
    beau = show_weather(lyon_coord, "weather_lyon")

    # Verdict « escapade » : croisement trajet + météo (cœur de l'angle produit)
    print("\n→ Verdict escapade")
    if beau:
        print(f"   ☀️  Beau temps à {lyon_name} : c'est le moment d'y aller en train !")
    elif beau is False:
        print(f"   🌧️  Météo maussade à {lyon_name} : peut-être une autre destination.")


if __name__ == "__main__":
    main()
