# Escapade sans voiture — « Où partir en train selon mes envies ? »

EFREI Paris · Learning XP – Tourisme en train · 8–12 juin 2026

**Équipe :** Zbiri Salah Eddine / Mouradi Iliasse / Haddam Rym / Touati Manal

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
  **durée de trajet max** · **date de l'escapade** (défaut : samedi prochain ;
  météo et horaires de train calculés pour ce jour).

## Données utilisées

| Source                         | Accès        | Rôle                                                                                                                          |
| ------------------------------ | ------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| API SNCF `/places`           | clé `.env` | résolution des gares (id, coordonnées)                                                                                       |
| API SNCF `/journeys`         | clé `.env` | durée +`co2_emission` du trajet, départ 8 h le jour choisi                                                                 |
| API SNCF `/isochrones`       | clé `.env` | zone atteignable en ≤ X h →**destinations candidates dynamiques** (croisée avec le référentiel des gares)           |
| Open-Meteo                     | sans clé     | météo à l'arrivée, à la date de l'escapade                                                                                |
| DATAtourisme                   | clé `.env` | **POIs labellisés tourisme** (mieux typés ; source principale)                                                         |
| OpenStreetMap / Overpass       | sans clé     | POIs à pied (repli si pas de clé DATAtourisme) + densité touristique des gares candidates                                   |
| OpenAgenda                     | clé `.env` | **événements à venir** par ville (info, hors score)                                                                   |
| `frequentation-gares` (SNCF) | sans clé     | **affluence** (voyageurs/an → critère « calme »)                                                                     |
| ADEME Impact CO2               | clé `.env` | CO₂ voiture officiel →**CO₂ économisé vs voiture** (repli : facteur SNCF ~89 g/km)                                  |
| `gares-de-voyageurs` (SNCF)  | sans clé     | référentiel des**2782 gares** ([build_gares.py](src/escapade/build_gares.py)) → sélecteur « gare de départ » complet |

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
  cosinus — affichées dans l'app et la CLI.

## Logique de scoring (guide 06 : min-max winsorisé + pondération justifiée)

Score composite par destination, chaque variable normalisée sur [0, 1]
(min-max **winsorisé** : bornes aux percentiles 10/90 dès 8 destinations, pour
qu'une ville atypique n'étire pas l'échelle) :

| Critère                 | Poids | Sens                                                              |
| ------------------------ | ----- | ----------------------------------------------------------------- |
| **affinité (ML)** | 0.30  | similarité cosinus intérêts ↔ profil d'activités de la ville |
| **soleil**         | 0.25  | indice météo à l'arrivée                                      |
| **calme**          | 0.20  | fréquentation**inversée** (moins de monde = mieux)        |
| **durée**         | 0.15  | trajet**inversé** (plus court = mieux)                     |
| **CO₂**           | 0.10  | émissions**inversées**                                    |

On affiche le **détail par critère**, pas seulement le score (honnêteté + soutenance).

Exemple de sortie réelle (depuis Paris Gare de Lyon · culture/gastronomie/patrimoine · 1 km · samedi 13/06/2026) :

```
#  Destination               Durée  Activ.  Affin.  Score
1  Annecy                     3h43     12    0.98   0.85
2  Avignon Centre             4h24     19    0.89   0.84
3  Montpellier Saint-Roch     4h38     16    0.85   0.78
🚆 Cap sur Annecy : plutôt ensoleillé, 3h43 de train — affinité 98%,
   ~61 kg CO₂ économisés vs voiture, 88 événements à venir.
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
streamlit run app.py             # http://localhost:8501

# Ligne de commande
python src/escapade/recommender.py "Paris Gare de Lyon" --interets culture,gastronomie,patrimoine --marche 1000
# --max génère aussi les destinations : gares à ≤ 3 h (isochrone SNCF) ; sans --max, liste fixe de 15 villes
# --date : météo et horaires de train pour ce jour (défaut : samedi prochain)
python src/escapade/recommender.py "Lille Flandres" --max 180 --top 5 --date 2026-06-20
```

## Structure

```
app.py                         interface Streamlit
src/escapade/
  recommender.py               moteur (collecte · score · CLI)
  isochrone.py                 destinations dynamiques (gares à ≤ X h, /isochrones,
                               classées par densité de POIs touristiques)
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

- **Sélection des destinations candidates** : dans l'isochrone, les gares
  (segments DRG A/B) sont présélectionnées par fréquentation puis **classées
  par densité de POIs touristiques** (OSM, 1 requête groupée mise en cache) —
  une mesure de l'intérêt touristique, plus un simple proxy d'affluence. Si
  Overpass échoue, repli sur le tri par fréquentation ; sans durée max
  (`--max`), repli sur la liste fixe de 15 villes.
- Météo = **prévision pour la date de l'escapade** (`--date`, défaut : samedi
  prochain) ; l'horizon Open-Meteo est d'~16 jours — au-delà, on sert le
  dernier jour prévisible.
- `/journeys` est interrogé pour **8 h du matin de la date choisie** (horaires
  théoriques si la date est future). Reste vrai : depuis une gare précise, un
  changement dans Paris (ex. vers Montparnasse) peut allonger le trajet.
- Comptage POIs Overpass = **richesse approximative** (pas de tri qualitatif) ;
  l'instance publique Overpass peut être lente → cache local indispensable.
- Normalisation **min-max winsorisée** (bornes p10–p90 dès 8 destinations) :
  une ville atypique n'étire plus l'échelle ; reste peu significative s'il
  demeure très peu de destinations.
