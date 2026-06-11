"""
POIs « à pied » autour d'une gare via OpenStreetMap / Overpass (sans clé).

Pour le recommandateur de tourisme SANS VOITURE : on compte les points d'intérêt
accessibles à pied (dans un rayon donné), par catégorie. Sert ensuite à scorer
et à lister les activités d'une destination.

Aucune dépendance : bibliothèque standard. Retry + miroir + cache + mode dégradé.
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

from escapade.paths import CACHE

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Instances Overpass (la 1re sature parfois -> miroir de secours)
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Catégories d'activités (centres d'intérêt grand public) -> filtres OSM.
# Une valeur préfixée par "~" est une regex (sélecteur Overpass ["k"~"regex"]).
_HIST = "~^(monument|memorial|castle|ruins|fort|monastery|church|tower|archaeological_site)$"
CATEGORIES = {
    "plage":       [("natural", "beach")],
    "nature":      [("leisure", "park"), ("leisure", "garden"), ("tourism", "viewpoint")],
    "culture":     [("tourism", "museum"), ("tourism", "gallery")],
    "patrimoine":  [("historic", _HIST), ("tourism", "attraction")],
    "gastronomie": [("amenity", "restaurant"), ("amenity", "cafe")],
}


def _selector(key, val):
    if val is None:
        return f'["{key}"]'
    if val.startswith("~"):
        return f'["{key}"~"{val[1:]}"]'
    return f'["{key}"="{val}"]'


def _build_query(lat, lon, radius):
    parts = []
    for filters in CATEGORIES.values():
        for key, val in filters:
            sel = _selector(key, val)
            for typ in ("node", "way"):
                parts.append(f"{typ}(around:{radius},{lat},{lon}){sel};")
    return f"[out:json][timeout:25];({''.join(parts)});out tags center;"


def _match(tags, key, val):
    if key not in tags:
        return False
    if val is None:
        return True
    if val.startswith("~"):
        return re.match(val[1:], tags[key]) is not None
    return tags[key] == val


def _classify(tags):
    cats = set()
    for cat, filters in CATEGORIES.items():
        if any(_match(tags, k, v) for k, v in filters):
            cats.add(cat)
    return cats


def _empty():
    return {"counts": {c: 0 for c in CATEGORIES}, "names": {c: [] for c in CATEGORIES}}


def _fetch(query):
    """Interroge Overpass avec retry/backoff et bascule de miroir."""
    body = urllib.parse.urlencode({"data": query}).encode()
    last_err = None
    for endpoint in OVERPASS_ENDPOINTS:
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    endpoint, data=body, headers={"User-Agent": "escapade-tourism/1.0"}
                )
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return json.load(resp)
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code in (429, 504, 503):      # surchargé : on attend et on réessaie
                    time.sleep(2 * (attempt + 1))
                    continue
                break
            except Exception as e:
                last_err = e
                time.sleep(2)
    raise last_err


# Cache partagé des densités touristiques : {"lat,lon": nb_pois}. Incrémental :
# seuls les points jamais comptés partent en requête (groupée, 1 seul appel).
DENSITY_CACHE = CACHE / "poi_density.json"


def tourist_density(points, radius=1000):
    """Nb de POIs touristiques (tourism/historic, OSM) autour de chaque point.

    Proxy de l'intérêt touristique d'une gare, utilisé pour pondérer la
    sélection des destinations candidates (la fréquentation seule favorise les
    gares pendulaires). Retourne une liste alignée sur `points`, ou None si
    Overpass est indisponible (→ l'appelant garde son tri de repli).
    """
    try:
        known = json.loads(DENSITY_CACHE.read_text(encoding="utf-8")) \
            if DENSITY_CACHE.exists() else {}
    except Exception:
        known = {}
    keys = [f"{lat:.4f},{lon:.4f}" for lat, lon in points]
    missing = [(k, p) for k, p in zip(keys, points) if k not in known]
    if missing:
        # une statement « union ; out count » par point : Overpass renvoie les
        # comptages dans l'ordre, le tout en un seul appel réseau
        parts = []
        for _, (lat, lon) in missing:
            parts.append(
                f"(node(around:{radius},{lat},{lon})[tourism];"
                f"way(around:{radius},{lat},{lon})[tourism];"
                f"node(around:{radius},{lat},{lon})[historic];);out count;"
            )
        try:
            raw = _fetch(f"[out:json][timeout:55];{''.join(parts)}")
            counts = [int(el["tags"]["total"]) for el in raw.get("elements", [])
                      if el.get("type") == "count"]
            if len(counts) != len(missing):
                return None
        except Exception as error:
            print(f"   ⚠️  Densité POI indisponible ({error}) → tri par fréquentation.")
            return None
        for (k, _), c in zip(missing, counts):
            known[k] = c
        CACHE.mkdir(exist_ok=True)
        DENSITY_CACHE.write_text(json.dumps(known), encoding="utf-8")
    return [known[k] for k in keys]


def get_pois(lat, lon, radius=1000, cache_name=None):
    """Retourne ({counts, names}, source) ; source = API / CACHE / VIDE."""
    cache_file = CACHE / f"poi_{cache_name}.json" if cache_name else None
    # Mode cache-first (interface) : cache servi sans appeler Overpass.
    if cache_file and cache_file.exists() and os.environ.get("RECO_CACHE_FIRST") == "1":
        return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
    try:
        raw = _fetch(_build_query(lat, lon, radius))
        result = _empty()
        for el in raw.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            for cat in _classify(tags):
                result["counts"][cat] += 1
                if name and name not in result["names"][cat] and len(result["names"][cat]) < 5:
                    result["names"][cat].append(name)
        if cache_file:
            CACHE.mkdir(exist_ok=True)
            cache_file.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        return result, "API"
    except Exception as error:
        if cache_file and cache_file.exists():
            print(f"   ⚠️  Overpass indisponible ({error}). Mode dégradé : cache local.")
            return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
        print(f"   ⚠️  Overpass indisponible ({error}) et pas de cache → 0 POI.")
        return _empty(), "VIDE"


if __name__ == "__main__":
    demo = [
        ("La Rochelle", 46.1527, -1.1455),
        ("Deauville",   49.3603,  0.0758),
        ("Strasbourg",  48.5850,  7.7350),
    ]
    for name, lat, lon in demo:
        res, src = get_pois(lat, lon, radius=1000, cache_name=name.lower().replace(" ", ""))
        c = res["counts"]
        print(f"\n{name}  [rayon 1 km · {src}]")
        for cat, n in sorted(c.items(), key=lambda x: -x[1]):
            ex = f"  ex: {', '.join(res['names'][cat][:3])}" if res["names"][cat] else ""
            print(f"   {cat:<12} {n:>3}{ex}")
        time.sleep(1)   # politesse Overpass (~1 req/s)
