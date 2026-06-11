# Escapade sans voiture — « Où partir en train selon mes envies ? »

EFREI Paris · Learning XP – Tourisme en train · 8–12 juin 2026
*(d'après `templates/readme_projet` — livrable + trace Portfolio « Gérer une base documentaire »)*

**Équipe :** Zbiri Salah Eddine
**Utilisateur cible :** grand public / touristes **sans voiture**
**Angle :** tourisme en train, activités accessibles **à pied**

---

## Problème

Décider d'une destination **sans voiture** est décourageant : il faut croiser à
la main les horaires de train, la météo, et surtout *« qu'est-ce que je pourrai
faire une fois là-bas, à pied ? »*. Une belle destination mal desservie à pied
devient inutile sans voiture.

## Solution

Un **recommandateur de destinations**. L'utilisateur renseigne ses critères ; le
service **classe les gares destination** et propose les meilleures, avec la
**liste des activités faisables à pied** à l'arrivée.

Paramètres saisis par l'utilisateur :

- **gare de départ** · **centres d'intérêt** (nature, culture, plage,
  patrimoine, gastronomie) · **aptitude à la marche** (rayon 500 m → 2 km) ·
  **durée de trajet max**.

## Données utilisées

| Source                         | Accès        | Rôle                                                      |
| ------------------------------ | ------------- | ---------------------------------------------------------- |
| API SNCF `/places`           | clé `.env` | résolution des gares (id, coordonnées)                   |
| API SNCF `/journeys`         | clé `.env` | durée +`co2_emission` du trajet                         |
| Open-Meteo                     | sans clé     | météo à l'arrivée                                      |
| DATAtourisme                   | clé `.env` | **POIs labellisés tourisme** (mieux typés ; source principale) |
| OpenStreetMap / Overpass       | sans clé     | POIs à pied (repli si pas de clé DATAtourisme)       |
| OpenAgenda                     | clé `.env` | **événements à venir** par ville (info, hors score) |
| `frequentation-gares` (SNCF) | sans clé     | **affluence** (voyageurs/an → critère « calme ») |
| ADEME Impact CO2 | clé `.env` | CO₂ voiture officiel → **CO₂ économisé vs voiture** (repli : facteur SNCF ~89 g/km) |
| `gares-de-voyageurs` (SNCF) | sans clé | référentiel des **2782 gares** ([build_gares.py](src/escapade/build_gares.py)) → sélecteur « gare de départ » complet |

Repli open data (mode dégradé) : `horaires-sncf` (ODbL).

## Machine Learning — deux briques explicables ([ml.py](src/escapade/ml.py))

**1. Affinité content-based (similarité cosinus).** Le critère « activités »
n'est pas un simple comptage :

- chaque destination = **vecteur de son profil d'activités** (nb de POIs par
  catégorie : plage, culture, patrimoine, nature, gastronomie) ;
- l'utilisateur = **vecteur de ses centres d'intérêt** cochés (0/1) ;
- **affinité = cosinus(profil, intérêts)** ∈ [0, 1] → mesure à quel point la ville
  correspond aux envies.

C'est du **filtrage content-based** (recommender system), explicable et sans boîte
noire : on sait toujours *pourquoi* une ville est proposée (ses POIs collent aux
catégories demandées). Pas de phase d'entraînement ici : la personnalisation
vient du vecteur utilisateur.

**2. Profils de villes (k-means, scikit-learn) — modèle appris.** Clustering
**non supervisé** des destinations sur leur **mix d'activités** (proportions de
POIs par catégorie, pas volumes : une petite ville très « patrimoine » rejoint
les grandes villes « patrimoine ») :

- **k choisi par score de silhouette** (2–5), `random_state` fixé → reproductible ;
- chaque cluster est **nommé d'après les catégories dominantes de son centroïde**
  (ex. « 🏛️ Patrimoine & culture ») → le modèle reste lisible ;
- alimente la fonctionnalité **« villes au même profil »** : si la 1re
  recommandation ne convient pas (déjà visitée, trop loin ce week-end), on
  propose des alternatives au **même ADN d'activités**, triées par similarité
  cosinus — affichées dans l'app, la CLI et le rapport HTML.

## Logique de scoring (guide 06 : min-max + pondération justifiée)

Score composite par destination, chaque variable sur [0, 1] :

| Critère                 | Poids | Sens                                                              |
| ------------------------ | ----- | ----------------------------------------------------------------- |
| **affinité (ML)** | 0.30  | similarité cosinus intérêts ↔ profil d'activités de la ville |
| **soleil**         | 0.25  | indice météo à l'arrivée                                      |
| **calme**          | 0.20  | fréquentation**inversée** (moins de monde = mieux)        |
| **durée**         | 0.15  | trajet**inversé** (plus court = mieux)                     |
| **CO₂**           | 0.10  | émissions**inversées**                                    |

On affiche le **détail par critère**, pas seulement le score (honnêteté + soutenance).

Exemple de sortie réelle (depuis Paris Gare de Lyon · culture/gastronomie/patrimoine · 1 km) :

```
#  Destination     Durée  Activ.  Affin.  Score
1  Lille Europe     1h31    412    0.82    0.77
2  Dijon            1h39    198    0.71    0.70
3  Avignon Centre   3h40    263    0.70    0.70
🚆 Cap sur Lille — affinité 82%, 1h31, calme 0.86.
```

## Preuve d'usage de l'API (vraie requête, pas une simulation)

```
$ export $(grep -v '^#' .env | xargs)          # clé chargée depuis .env
$ curl -sS -o /dev/null -w "HTTP %{http_code}\n" -u "$SNCF_API_KEY:" \
    "https://api.sncf.com/v1/coverage/sncf/journeys?from=stop_area:SNCF:87686006&to=stop_area:SNCF:87723197"
HTTP 200
```

(Paris Gare de Lyon → Lyon Part-Dieu. La clé n'apparaît jamais en clair.)

## Lancer le projet

**Prérequis :** Python 3.11+ et `pip install -r requirements.txt`.

Créer un fichier `.env` à la racine (jamais commité — guide 03) :

```
SNCF_API_KEY=votre_cle
DATATOURISME_KEY=votre_cle          # POIs (sinon repli OpenStreetMap)
OPENAGENDA_KEY=votre_cle_publique   # optionnel (événements)
ADEME_KEY=votre_cle                 # optionnel (CO₂ vs voiture officiel)
```

```bash
# (Optionnel) référentiel complet des gares pour le sélecteur de départ
python src/escapade/build_gares.py   # -> data/gares_france.parquet (2782 gares)

# Interface web interactive (recommandée)
streamlit run app.py             # http://localhost:8502

# Ligne de commande
python src/escapade/recommender.py "Paris Gare de Lyon" --interets culture,gastronomie,patrimoine --marche 1000
python src/escapade/recommender.py "Lille Flandres" --max 180 --top 5
python src/escapade/recommender.py --html   # rapport visuel (carte Leaflet + cartes)
```

## Structure
```
app.py                         interface Streamlit
src/escapade/
  recommender.py               moteur (collecte · score · CLI · rapport HTML)
  sncf.py                      accès API SNCF (cache + mode dégradé)
  ml.py                        ML : affinité cosinus + profils de villes (k-means)
  paths.py                     chemins projet + chargement .env
  build_gares.py               génère data/gares_france.parquet (gares-de-voyageurs)
  sources/                     connecteurs de données
    poi_datatourisme.py · poi_osm.py · events.py · ademe.py
data/        gares_france.parquet          docs/   livrables (cadrage, checklist)
cache/       réponses API (gitignore)      exemples_json/  échantillons de secours
```

## Mode dégradé

Toutes les sources passent par une fonction unique avec **cache JSON local** et
repli automatique. Avec `RECO_CACHE_FIRST=1`, l'interface sert directement le
cache (rapide, hors-ligne). `.env` et `cache/` sont dans le `.gitignore` ; des
échantillons réels annotés sont versionnés dans [`exemples_json/`](exemples_json/).

## Limites connues

- **Destinations codées en dur** (15 villes touristiques) ; piste : destinations
  dynamiques (atteignables en ≤ X h).
- Météo = **prévision du jour**, pas la date exacte du week-end visé.
- `/journeys` part de l'heure courante ; depuis une gare précise, un changement
  dans Paris (ex. vers Montparnasse) peut allonger le trajet.
- Comptage POIs Overpass = **richesse approximative** (pas de tri qualitatif) ;
  l'instance publique Overpass peut être lente → cache local indispensable.
- Normalisation **min-max sensible aux valeurs extrêmes** (une ville atypique
  étire l'échelle) et peu significative s'il reste peu de destinations.

