"""
Interface Streamlit — recommandateur de destinations en train SANS VOITURE.
L'utilisateur règle ses paramètres ; on classe les destinations et on liste les
activités accessibles à pied.

Lancer :  streamlit run app.py
"""
import os
import sys
from pathlib import Path

# Cache-first : l'interface sert les données en cache sans attendre les API lentes
# (réseau uniquement si une donnée n'a jamais été récupérée). DOIT précéder l'import.
os.environ.setdefault("RECO_CACHE_FIRST", "1")

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import pandas as pd
import pydeck as pdk
import streamlit as st

from escapade.recommender import collect, score_rows
from escapade.sources import poi_osm as poi

st.set_page_config(page_title="Escapade sans voiture", page_icon="🚆", layout="wide")


# Grandes gares TGV de départ mises en tête (certaines, comme « Paris Gare de
# Lyon », ne figurent pas telles quelles dans le dataset gares-de-voyageurs).
TOP_GARES = [
    "Paris Gare de Lyon", "Paris Montparnasse", "Paris Nord", "Paris Est",
    "Lyon Part-Dieu", "Marseille Saint-Charles", "Lille Flandres",
    "Bordeaux Saint-Jean", "Nantes", "Strasbourg",
]


@st.cache_data(show_spinner=False)
def station_names():
    """Liste des gares : grandes gares TGV en tête, puis le référentiel complet."""
    ref = Path(__file__).resolve().parent / "data" / "gares_france.parquet"
    rest = []
    if ref.exists():
        rest = sorted(pd.read_parquet(ref)["name"].dropna().unique().tolist())
    seen = set(TOP_GARES)
    return TOP_GARES + [n for n in rest if n not in seen]


@st.cache_data(show_spinner=False)
def run_reco(origin, interests, radius, max_min):
    origin_name, origin_coord, rows = collect(origin, list(interests), radius)
    if max_min:
        rows = [r for r in rows if r["minutes"] <= max_min]
    classement = score_rows(rows) if rows else []
    return origin_name, origin_coord, classement


st.title("🚆 Où partir en train, sans voiture ?")
st.caption(
    "Destinations accessibles en train, classées selon vos envies et "
    "ce qu'on peut y faire à pied (trajet · météo · activités · affluence)."
)

with st.sidebar:
    st.header("Vos critères")
    gares = station_names()
    default = next((i for i, n in enumerate(gares) if n.startswith("Paris")), 0)
    origin = st.selectbox("Gare de départ", gares, index=default)
    interests = st.multiselect(
        "Centres d'intérêt", list(poi.CATEGORIES),
        default=["culture", "gastronomie", "patrimoine"],
    )
    radius = st.select_slider(
        "Aptitude à la marche", options=[500, 1000, 1500, 2000], value=1000,
        format_func=lambda x: f"{x} m",
    )
    max_min = st.slider("Durée de trajet max (min)", 60, 360, 240, step=30)
    go = st.button("Rechercher", type="primary", use_container_width=True)

if not interests:
    st.warning("Choisissez au moins un centre d'intérêt.")
    st.stop()

with st.spinner("Calcul des destinations (trajets, météo, activités à pied)…"):
    origin_name, origin_coord, classement = run_reco(
        origin, tuple(interests), radius, max_min
    )

if not classement:
    st.error("Aucune destination exploitable pour ces critères.")
    st.stop()

best = classement[0]
ville = best["ville"].split("(")[0].strip()

c1, c2, c3 = st.columns(3)
c1.metric("🥇 Recommandation", ville, f"{best['affinite']:.0%} d'affinité")
_eco = best.get("co2_economie")
c2.metric("🚆 Trajet", f"{best['minutes'] // 60}h{best['minutes'] % 60:02d}",
          f"−{_eco:.0f} kg CO₂ vs voiture" if _eco else f"{best['co2']:.0f} g CO₂")
c3.metric("🎯 Affinité (ML)", f"{best['affinite']:.0%}", f"{best['activites_raw']} activités")

col_map, col_rank = st.columns([3, 2])

with col_map:
    pts = []
    for r in classement:
        lat, lon = r["coord"]
        if lat is None:
            continue
        s = r["score"]
        pts.append({
            "ville": r["ville"].split("(")[0].strip(),
            "lat": lat, "lon": lon, "score": round(s, 2),
            "color": [int(60 + 195 * (1 - s)), int(60 + 195 * s), 80, 200],
        })
    layer = pdk.Layer(
        "ScatterplotLayer", pd.DataFrame(pts),
        get_position="[lon, lat]", get_fill_color="color",
        get_radius="8000 + score * 32000", pickable=True,
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=pdk.ViewState(latitude=46.6, longitude=2.5, zoom=4.6),
        map_style="light",
        tooltip={"text": "{ville}\nscore {score}"},
    ))

with col_rank:
    st.subheader("Classement")
    table = [{
        "Ville": r["ville"].split("(")[0].strip(),
        "Durée": f"{r['minutes'] // 60}h{r['minutes'] % 60:02d}",
        "Affinité": f"{r['affinite']:.0%}",
        "Activités": r["activites_raw"],
        "Événements": r.get("events", 0),
        "Foule (k/an)": (r["frequentation"] // 1000 if r["frequentation"] else None),
        "Score": round(r["score"], 2),
    } for r in classement]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

st.subheader(f"🚶 À faire à pied à {ville}")
cols = st.columns(len(interests))
for col, cat in zip(cols, interests):
    col.metric(cat.capitalize(), best["poi_counts"].get(cat, 0))
    names = best["poi_names"].get(cat, [])
    if names:
        col.caption(" · ".join(names[:4]))
