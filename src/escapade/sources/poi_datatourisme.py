"""
POIs « à pied » via DATAtourisme (POIs labellisés tourisme, mieux catégorisés
que l'OSM brut). Drop-in de poi.py : même CATEGORIES et même get_pois().

API : /v1/catalog?api_key=…&geo_distance=lat,lng,Rkm&size=250
Clé dans .env (DATATOURISME_KEY). Cache + mode dégradé (préfixe « dt_ »).
"""
import json
import os
import sys
import urllib.parse
import urllib.request

from escapade.paths import CACHE, load_env

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://api.datatourisme.fr/v1/catalog"
load_env()  # clé lue au moment de l'appel

# Mêmes catégories que poi.py (clés identiques pour l'affinité ML)
CATEGORIES = {"plage": [], "nature": [], "culture": [], "patrimoine": [], "gastronomie": []}

# Types de l'ontologie DATAtourisme -> nos catégories (un objet peut en cumuler)
_MAP = {
    "plage": {"Beach"},
    "nature": {"NaturalHeritage", "ParkAndGarden", "Garden", "Park"},
    "culture": {"Museum", "ArtGalleryOrExhibitionGallery", "InterpretationCentre",
                "Theater", "Cinema", "EntertainmentAndEvent", "Casino"},
    "patrimoine": {"ReligiousSite", "RemarkableBuilding", "ArcheologicalSite",
                   "Castle", "DefensiveSite", "Memorial", "CulturalSite"},
    "gastronomie": {"FoodEstablishment", "Restaurant", "BarOrPub", "WineCellar"},
}


def _classify(types):
    ts = set(types)
    cats = {c for c, keys in _MAP.items() if ts & keys}
    # « CulturalSite » seul (sans sous-type culture) reste du patrimoine
    if "culture" in cats and "patrimoine" in cats and not (ts & (_MAP["culture"])):
        cats.discard("culture")
    return cats


def _empty():
    return {"counts": {c: 0 for c in CATEGORIES}, "names": {c: [] for c in CATEGORIES}}


def get_pois(lat, lon, radius=1000, cache_name=None):
    """Retourne ({counts, names}, source) ; source = API / CACHE / VIDE."""
    cache_file = CACHE / f"dt_{cache_name}.json" if cache_name else None
    if cache_file and cache_file.exists() and os.environ.get("RECO_CACHE_FIRST") == "1":
        return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
    try:
        key = os.environ.get("DATATOURISME_KEY")
        if not key:
            raise RuntimeError("DATATOURISME_KEY absente")
        km = max(1, round(radius / 1000))
        url = BASE + "?" + urllib.parse.urlencode({
            "api_key": key, "geo_distance": f"{lat},{lon},{km}km", "size": 250,
        })
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.load(resp)
        result = _empty()
        for obj in data.get("objects", []):
            label = obj.get("label")
            if isinstance(label, dict):
                label = label.get("@fr") or label.get("@en") or next(iter(label.values()), None)
            for cat in _classify(obj.get("type", [])):
                result["counts"][cat] += 1
                if label and label not in result["names"][cat] and len(result["names"][cat]) < 5:
                    result["names"][cat].append(label)
        if cache_file:
            CACHE.mkdir(exist_ok=True)
            cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result, "API"
    except Exception as error:
        if cache_file and cache_file.exists():
            print(f"   ⚠️  DATAtourisme indisponible ({error}). Cache local.")
            return json.loads(cache_file.read_text(encoding="utf-8")), "CACHE"
        print(f"   ⚠️  DATAtourisme indisponible ({error}) → 0 POI.")
        return _empty(), "VIDE"


if __name__ == "__main__":
    for name, la, lo in [("Lyon", 45.7605, 4.8594), ("La Rochelle", 46.1527, -1.1455)]:
        res, src = get_pois(la, lo, 1000, name.lower())
        print(name, src, {c: n for c, n in res["counts"].items()})
