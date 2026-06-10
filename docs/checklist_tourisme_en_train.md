# ✅ Checklist – Learning XP « Tourisme en train »

EFREI Paris · 8–12 juin 2026
Données : ressources.data.sncf.com · data.gouv.fr · ADEME

> Principe n°1 : **aucune fonctionnalité ne doit dépendre uniquement de l'API.** Chaque feature qui appelle l'API a une version de repli (cache JSON local / fichiers téléchargés).

---

## 0. À faire AVANT lundi (urgent ⏰)

- [x] **S'inscrire à l'API SNCF dès dimanche soir / lundi 7h** : https://numerique.sncf.com/startup/api/token-developpeur/ → formulaire (nom, email, organisation) + CGU. La clé est active en quelques minutes *mais ce n'est pas garanti*.
- [ ] **Une clé par coéquipier** (quota = 5 000 req/jour/clé).
- [x] **Demander la clé ADEME Impact CO2 le plus tôt possible** : email à `impactco2@ademe.fr` (délai variable). Repli si pas reçue : le champ `co2_emission` renvoyé par `/journeys`.
- [x] En attendant la clé : préparer les **réponses JSON de secours** (cf. section 5).

---

## 1. Configuration API SNCF (la SEULE valide)

- [x] Base : `https://api.sncf.com/v1`
- [x] Coverage : `sncf`
- [x] Auth : **HTTP Basic** → clé = *username*, mot de passe **vide** (d'où le `:` final)
- [x] Clé passée dans le **header Authorization**, **jamais dans l'URL**
- [x] Quotas : **5 000 req/jour/clé** · 150 000 req/mois temps réel (~3,5 req/min)

> ⚠️ **Ne PAS suivre** les vieux tutos Navitia : `navitia.io`, coverages régionaux, token Bearer, quota 3 000/jour → tout faux pour ce hackathon.

- [ ] Doc de référence : https://doc.navitia.io (remplacer la racine par `api.sncf.com`)
- [ ] Test interactif : https://playground.navitia.io

---

## 2. Sécurité de la clé (non négociable 🔒)

- [x] Clé dans un fichier **`.env`** à la racine (nom exact)
- [x] `.env` est dans le **`.gitignore`** (déjà fait dans le repo)
- [ ] **Lire `git status` avant CHAQUE commit** → aucune clé, aucun `.env`
- [ ] Vérifier : `git check-ignore .env` doit afficher `.env`
- [x] **Ne PAS créer de `.env.example`** versionné (le `.gitignore` ignore aussi `.env.*`) → partager le format dans le README
- [x] Toutes les clés (SNCF, ADEME, DATAtourisme, OpenAgenda…) dans le **même `.env`**
- [ ] Si une clé fuite : la **régénérer immédiatement** depuis le portail + nettoyer l'historique Git si besoin

Contenu du `.env` :
```
SNCF_API_KEY=collez_votre_cle_ici
```

Lecture de la clé :
- Shell : `export $(grep -v '^#' .env | xargs)`
- Python : `from dotenv import load_dotenv; load_dotenv(); key = os.environ["SNCF_API_KEY"]`
- Node : `import 'dotenv/config'; const key = process.env.SNCF_API_KEY;`

---

## 3. Requêtes API (pré-testées le 07/06/2026)

> 💡 **Piège n°1** : un arrêt n'est pas une gare. **Toujours résoudre l'id via `/places` AVANT** `/journeys` ou `/departures`. Ne jamais copier un id d'un vieux tuto/forum/IA.
> 💻 **Sous Windows** : lancer dans **Git Bash** (pas PowerShell/cmd).
> 👁️ Lisibilité : ajouter ` | python3 -m json.tool` à la fin.

- [x] **Résoudre une gare** → `/places?q=...` puis récupérer `places[].id` de type `stop_area` (ex. `stop_area:SNCF:87686006`)
- [x] **Itinéraire** → `/journeys?from=...&to=...&datetime=AAAAMMJJTHHMMSS&disable_geojson=true` → contient `sections[]` + `co2_emission` (argument carbone sans appel externe)
- [x] **Temps réel** → ajouter `data_freshness=realtime` (sinon horaire théorique). Couvre TGV/TER/Intercités/Lyria/Eurostar ; **Transilien = planifié uniquement**
- [x] **Prochains départs** → `/stop_areas/{id}/departures?from_datetime=...&count=20&data_freshness=realtime`
- [x] **Perturbations** (optionnel) → `/disruptions?count=20`
- [ ] `/isochrones` existe mais est en **bêta** (réserver aux équipes à l'aise, avec `disable_geojson=true`)

Gestion des erreurs :
- [x] **401** → vérifier clé, `:` final, header
- [x] **404** → repasser par `/places` pour le bon id
- [x] **429** → **ne pas relancer tout de suite** : backoff ≥ 30 s puis mode dégradé

---

## 4. Mode dégradé (la démo doit marcher sans réseau)

- [x] Sauvegarder **5 à 10 réponses JSON valides** par fonctionnalité dépendant de l'API
- [ ] Télécharger les **fichiers GTFS** des lignes utiles en local
- [x] Prévoir dans le code un **interrupteur** : si l'API échoue / quota proche → lire le fichier local
- [x] **Seuil de bascule conseillé : ~3 000 req/jour** (sur 5 000)
- [x] ⚠️ **Ne pas committer de gros fichiers** (GTFS, caches) → dossier `cache/` déjà ignoré. Versionner seulement de **petits échantillons JSON annotés** + les instructions de téléchargement

Datasets SNCF (sur `ressources.data.sncf.com/explore/dataset/{slug}`, licence ODbL) :
- [ ] `horaires-sncf` – temps de trajet, itinéraires, fréquences
- [x] `gares-de-voyageurs` – localisation, code UIC, géoloc, commune
- [x] `frequentation-gares` – attractivité d'une gare (2015–2024)
- [ ] `equipements-accessibilite-sncf` – service PMR, score accessibilité
- [x] `emission-co2-perimetre-complet` – train / voiture / avion
- [ ] `emission-co2-perimetre-usage` – empreinte carbone (énergie seule)
- [ ] `tgvmax` – tarification jeune (places MAX JEUNE/SENIOR, 30 j glissants)

> 💡 Onglet **« API »** d'OpenDataSoft = génère l'URL d'export JSON/CSV.

Flux temps réel sans clé (`proxy.transport.data.gouv.fr/resource/`) : `sncf-gtfs-rt-trip-updates`, `sncf-gtfs-rt-service-alerts`, `sncf-siri-lite-estimated-timetable`, `sncf-siri-lite-situation-exchange` *(noms à reconfirmer le jour J)*.

---

## 5. Données externes (vérifiées le 06/06/2026)

- [x] **DATAtourisme** (POI touristiques) → API `api.datatourisme.fr` (clé self-service) **ou** CSV régionaux. *Repli sûr = CSV pré-téléchargés.*
- [x] **ADEME Impact CO2** (comparaison carbone) → clé par email. *Repli = `co2_emission` de `/journeys`.*
- [x] **OpenAgenda** (événements culturels) → API **v2**, clé publique en header (l'ancien `/events.json` est retiré)
- [x] **Open-Meteo** (météo/climat) → `api.open-meteo.com`, **sans clé** (préféré à Météo-France)
- [ ] **geo.api.gouv.fr** (communes INSEE) → sans clé
- [ ] **Base Adresse Nationale** (géocodage) → `adresse.data.gouv.fr`, sans clé
- [x] **OpenStreetMap / Overpass** (carte, routing) → ~1 req/s, pré-télécharger les POI d'une zone restreinte

> Règle : privilégier les sources **sans clé** pour aller vite + **exports statiques** pour le mode dégradé. Seule démarche à anticiper = clé ADEME.

---

## 6. Score composite (si projet de classement)

- [x] Choisir **2–4 variables numériques** comparables (fréquentation, nb POI, régularité, accessibilité…)
- [x] **Normaliser** chaque variable sur [0,1] : `x_norm = (x - min) / (max - min)`
- [x] Si « meilleur = bas » (ex. CO₂) → inverser avec `1 - x_norm`
- [x] **Pondérer + additionner + trier**
- [x] **Justifier les pondérations** en soutenance (logique explicable, pas formule magique)
- [x] Assumer les limites (min-max sensible aux valeurs extrêmes)
- [x] Montrer le **détail par critère**, pas que le score final

---

## 7. Livrables (Portfolio)

### Fiche de cadrage produit (lundi, en équipe, 1 page)
- [x] Problème précis (situation réelle, pas catégorie vague)
- [x] Utilisateur cible (profil, contexte, contrainte : sans voiture, PMR, budget…)
- [x] Solution = un **service** (entrée → traitement → réponse utile), **pas un dashboard**
- [x] Données nécessaires (datasets SNCF + externes + rôle de l'API : central/complément/aucun)
- [x] MVP réaliste (jeudi)
- [x] Mode dégradé prévu
- [x] Angle et différenciation (affluence/temps réel · PMR · tarif jeune/TGVmax · autre)

### README projet (rempli au fil de la semaine, finalisé jeudi)
- [ ] Nom du projet, équipe, angle
- [x] Problème + utilisateur
- [x] Solution (entrée → traitement → réponse)
- [x] Tableau des données utilisées (source / URL / champs)
- [x] Logique de scoring / recommandation (pondérations, règles, tri + pourquoi)
- [x] **Preuve d'usage de l'API** : capture/log d'une **vraie requête** (pas une simulation)
- [x] Limites connues
- [x] Comment lancer le projet (prérequis, install, `.env`)

---

## 8. Publier en open data (optionnel, valorisation)

- [ ] Compte gratuit sur **data.gouv.fr**
- [ ] « Mes réutilisations » → créer une réutilisation
- [ ] Renseigner : Titre, URL publique, Type, Thématique, Description
- [ ] **Lier les jeux de données sources** (SNCF, ADEME…)
- [ ] Ajouter une image / capture
- [ ] Publier → passe par une **modération**
- [ ] Côté SNCF (optionnel) : signaler à `open-data@sncf.fr`
- [ ] À considérer comme suite : **Open Data University** (Saison 5 dès sept. 2026, `open-data-university@latitudes.cc`)

> Doc officielle : guides.data.gouv.fr
