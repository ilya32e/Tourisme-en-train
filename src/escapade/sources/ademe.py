"""
ADEME Impact CO2 — comparaison carbone par mode de transport.
GET /api/v1/transport?km=X (Authorization: Bearer) -> kg CO₂e par mode.
Sert à estimer le CO₂ « voiture thermique » officiel pour une distance.
Clé dans .env (ADEME_KEY). Cache + mode dégradé (RECO_CACHE_FIRST).
"""
import json
import os
import sys
import urllib.parse
import urllib.request

from escapade.paths import CACHE, load_env

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://impactco2.fr/api/v1/transport"
load_env()


def get_car_kg(km, cache_name=None):
    """CO₂ (kg) d'une voiture thermique solo pour `km` (None si indispo)."""
    cache_file = CACHE / f"ademe_{cache_name}.json" if cache_name else None
    if cache_file and cache_file.exists() and os.environ.get("RECO_CACHE_FIRST") == "1":
        return json.loads(cache_file.read_text(encoding="utf-8")).get("car_kg")

    key = os.environ.get("ADEME_KEY")
    if not key:
        return None
    try:
        url = BASE + "?" + urllib.parse.urlencode({"km": round(km, 1)})
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.load(r).get("data", [])
        car = next((x["value"] for x in data if x.get("name") == "Voiture thermique"), None)
        if cache_file and car is not None:
            CACHE.mkdir(exist_ok=True)
            cache_file.write_text(json.dumps({"car_kg": car, "km": km}), encoding="utf-8")
        return car
    except Exception:
        if cache_file and cache_file.exists():
            return json.loads(cache_file.read_text(encoding="utf-8")).get("car_kg")
        return None


if __name__ == "__main__":
    print("Voiture thermique, 400 km :", round(get_car_kg(400) or 0, 1), "kg CO2e")
