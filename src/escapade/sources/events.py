"""
Événements à venir par ville (OpenAgenda API v2).

L'API publique ne permet pas la recherche globale ; on identifie l'agenda de
tourisme de la ville et on compte ses événements à venir. Info affichée par
destination (« N événements à venir »). Clé dans .env (OPENAGENDA_KEY).
Cache + mode dégradé (RECO_CACHE_FIRST).
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from escapade.paths import CACHE, load_env

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "https://api.openagenda.com/v2"
load_env()


def _city(name):
    name = name.split("(")[0].strip()
    parts = name.split()
    if parts and parts[0] in {"La", "Le", "Les", "Saint", "Sainte", "St"}:
        return " ".join(parts[:2])
    return parts[0] if parts else name


def _api(path, params, key):
    url = f"{BASE}{path}?" + urllib.parse.urlencode({**params, "key": key})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1)); continue
            return {}
        except Exception:
            time.sleep(1); continue
    return {}


def get_events(name, cache_name=None):
    """Nombre d'événements à venir dans la ville (0 si pas de clé/agenda)."""
    cache_file = CACHE / f"events_{cache_name}.json" if cache_name else None
    if cache_file and cache_file.exists() and os.environ.get("RECO_CACHE_FIRST") == "1":
        return json.loads(cache_file.read_text(encoding="utf-8")).get("count", 0)

    key = os.environ.get("OPENAGENDA_KEY")
    count = 0
    if key:
        city = _city(name)
        uid = None
        for q in (f"{city} tourisme", city):
            ag = _api("/agendas", {"search": q, "size": 1}, key).get("agendas", [])
            if ag:
                uid = ag[0]["uid"]; break
        if uid:
            count = _api(f"/agendas/{uid}/events", {"relative[]": "upcoming", "size": 1}, key).get("total", 0)

    if cache_file:
        CACHE.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps({"count": count}), encoding="utf-8")
    return count


if __name__ == "__main__":
    for v in ["Lyon Part Dieu (Lyon)", "Bordeaux Saint-Jean", "La Rochelle"]:
        print(v, "->", get_events(v, None), "événements à venir")
