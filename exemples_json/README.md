# Échantillons JSON de secours (mode dégradé)

Preuve du **principe n°1** : la démo tourne sans réseau. Ces fichiers sont des
extraits **réels** (champs utiles seulement) de réponses d'API mises en cache.

| Fichier | Source | Régénérer |
|---|---|---|
| `journey_paris_lyon.sample.json` | API SNCF `/journeys` | `python src/escapade/recommender.py` |
| `weather.sample.json` | Open-Meteo `/forecast` | `python src/escapade/recommender.py` |

Les clés du cache incluent désormais la **date de l'escapade**
(ex. `journey_<origine>_<dest>_AAAAMMJJ.json`, `weather_<ville>_AAAAMMJJ.json`) :
trajets et météo sont calculés pour le jour choisi, pas pour « maintenant ».

## Mécanisme réel
Le cache complet vit dans `cache/` (ignoré par Git car volumineux). À chaque appel
réussi, la réponse y est sauvegardée ; si l'API échoue (réseau, quota 429), le
code rejoue le fichier local. Avec `RECO_CACHE_FIRST=1`, le cache est servi
directement (rapide, hors-ligne).

Ces deux échantillons sont versionnés pour documenter le format ; les réponses
complètes se régénèrent en relançant le script (elles repeuplent `cache/`).
