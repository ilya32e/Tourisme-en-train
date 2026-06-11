"""
Destinations dynamiques : gares atteignables en ≤ X heures (isochrone SNCF).

Remplace la liste fixe de destinations : l'API /isochrones donne la zone
atteignable en train depuis la gare de départ ; on garde les gares du
référentiel (data/gares_france.parquet) situées dedans, puis on retient les
N plus fréquentées (export open data frequentation-gares, 1 appel mis en
cache), suffisamment éloignées entre elles — et de l'origine — pour varier
les propositions. Tout échec (API, parquet absent…) retourne None → le
moteur replie sur la liste fixe (mode dégradé, comme partout ailleurs).
"""
import math
from datetime import date

from escapade.paths import DATA
from escapade.sncf import api_get, http_get_json

N_DEFAULT = 15        # nb de candidates : chaque destination coûte ~5 appels API
MIN_KM_ORIGINE = 25   # écarte la banlieue immédiate (escapade, pas trajet du quotidien)
MIN_KM_ENTRE = 20     # 1 gare par zone : évite 4 gares de la même agglomération
TGV_KM_H = 320        # vitesse max train : préfiltre distance avant le test polygone

FREQ_EXPORT = ("https://ressources.data.sncf.com/api/explore/v2.1/catalog/"
               "datasets/frequentation-gares/exports/json"
               "?select=code_uic_complet,total_voyageurs_2024")


def _haversine_km(a, b):
    (la1, lo1), (la2, lo2) = a, b
    dla, dlo = math.radians(la2 - la1), math.radians(lo2 - lo1)
    h = (math.sin(dla / 2) ** 2
         + math.cos(math.radians(la1)) * math.cos(math.radians(la2)) * math.sin(dlo / 2) ** 2)
    return 2 * 6371 * math.asin(math.sqrt(h))


def _in_ring(lon, lat, ring):
    """Point dans un anneau (ray casting, geojson = [lon, lat])."""
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _prepare_polygons(coords):
    """Pré-calcule la bbox de chaque polygone : un MultiPolygon d'isochrone
    compte des centaines d'anneaux, la bbox écarte presque tous les tests."""
    polys = []
    for poly in coords:  # poly = [anneau extérieur, trous éventuels...]
        outer = poly[0]
        lons = [p[0] for p in outer]
        lats = [p[1] for p in outer]
        polys.append((min(lons), max(lons), min(lats), max(lats), poly))
    return polys


def _in_isochrone(lon, lat, polys):
    for lo1, lo2, la1, la2, poly in polys:
        if not (lo1 <= lon <= lo2 and la1 <= lat <= la2):
            continue
        if _in_ring(lon, lat, poly[0]) and not any(_in_ring(lon, lat, h) for h in poly[1:]):
            return True
    return False


def _frequentations():
    """uic -> voyageurs/an (export complet, 1 appel, mis en cache)."""
    try:
        data, _ = http_get_json(FREQ_EXPORT, "freq_gares_export")
        return {str(g.get("code_uic_complet")): g.get("total_voyageurs_2024") or 0
                for g in data}
    except (Exception, SystemExit):  # classement par fréquentation = optionnel
        return {}


def reachable_destinations(origin_id, origin_slug, origin_coord, max_minutes, n=N_DEFAULT):
    """Gares candidates à ≤ max_minutes de train depuis l'origine.

    Retourne une liste de {id, name, coord} (les champs qu'aurait donnés
    /places, mais sans appel : ils sont déjà dans le référentiel), ou None
    si la génération dynamique est impossible → repli liste fixe.
    """
    parquet = DATA / "gares_france.parquet"
    if not parquet.exists() or None in origin_coord:
        return None
    try:
        import pandas as pd

        data, _ = api_get(
            "/isochrones",
            {"from": origin_id, "boundary_duration[]": max_minutes * 60,
             "datetime": f"{date.today():%Y%m%d}T080000"},  # départ le matin
            f"iso_{origin_slug}_{max_minutes}",
        )
        isos = data.get("isochrones", [])
        gj = isos[0].get("geojson", {}) if isos else {}
        coords = gj.get("coordinates", [])
        if not coords:
            return None
        if gj.get("type") == "Polygon":
            coords = [coords]
        polys = _prepare_polygons(coords)

        df = pd.read_parquet(parquet).dropna(subset=["lat", "lon"])
        # grandes gares et gares régionales (A/B) : on écarte les haltes locales
        if "segment_drg" in df.columns:
            df = df[df["segment_drg"].isin(["A", "B"])]
        freq = _frequentations()
        max_km = max_minutes / 60 * TGV_KM_H  # plus loin = inatteignable en train

        candidates = []
        for g in df.itertuples():
            if not (MIN_KM_ORIGINE <= _haversine_km(origin_coord, (g.lat, g.lon)) <= max_km):
                continue
            if not _in_isochrone(g.lon, g.lat, polys):
                continue
            uic = None if pd.isna(g.uic) else str(g.uic)
            sa_id = getattr(g, "stop_area_id", None)
            if not sa_id and uic:
                sa_id = f"stop_area:SNCF:{uic}"
            if not sa_id:
                continue
            candidates.append({"id": sa_id, "name": g.name, "coord": (g.lat, g.lon),
                               "freq": freq.get(uic, 0),
                               "segment": getattr(g, "segment_drg", None)})

        # grandes gares (A) d'abord — la fréquentation seule ferait remonter la
        # banlieue pendulaire (Melun, Cergy…) avant Reims ou Rouen — puis les
        # régionales (B) en complément ; 1 gare max par zone de MIN_KM_ENTRE km
        candidates.sort(key=lambda c: (c["segment"] != "A", -c["freq"]))
        kept = []
        for c in candidates:
            if all(_haversine_km(c["coord"], k["coord"]) >= MIN_KM_ENTRE for k in kept):
                kept.append(c)
            if len(kept) == n:
                break
        return kept or None

    except (Exception, SystemExit) as error:  # api_get sans cache lève SystemExit
        print(f"   ⚠️  Isochrone indisponible ({error}) → repli sur la liste fixe.")
        return None
