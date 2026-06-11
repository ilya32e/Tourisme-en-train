"""
Génère data/gares_france.parquet — référentiel complet des gares françaises
(dataset open data SNCF `gares-de-voyageurs`, sans clé). Sert à l'interface
Streamlit pour proposer toutes les gares de départ (pas seulement les grandes
gares TGV de TOP_GARES).

Lancement :  python src/escapade/build_gares.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

from escapade.paths import DATA
from escapade.sncf import http_get_json

URL = (
    "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets/"
    "gares-de-voyageurs/exports/json"
)


def main():
    data, source = http_get_json(URL, "gares_france_export")
    rows = [
        {
            "name": gare["nom"],
            "uic": gare.get("codes_uic"),
            "lat": gare.get("position_geographique", {}).get("lat"),
            "lon": gare.get("position_geographique", {}).get("lon"),
        }
        for gare in data
        if gare.get("nom")
    ]
    df = pd.DataFrame(rows).drop_duplicates(subset="name").sort_values("name")

    DATA.mkdir(exist_ok=True)
    out = DATA / "gares_france.parquet"
    df.to_parquet(out, index=False)
    print(f"✓ {len(df)} gares -> {out}  [source : {source}]")


if __name__ == "__main__":
    main()
