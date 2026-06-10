# Fiche de cadrage produit

EFREI Paris · Learning XP – Tourisme en train · 8–12 juin 2026

**Équipe :** … · **Date :** lundi 8 juin 2026

---

## 1. Problème
Décider d'une destination **sans voiture** est décourageant : il faut croiser à
la main les horaires de train, la météo, et surtout *« qu'est-ce que je pourrai
faire une fois là-bas, à pied ? »*. Une belle destination mal desservie à pied
devient inutile sans voiture.

## 2. Utilisateur cible
**Grand public / touristes sans voiture** (ou qui veulent laisser la leur) :
étudiant, jeune actif, famille, touriste, qui cherche où aller en train pour
faire des **activités accessibles à pied**.

## 3. Solution : un service
Un **recommandateur de destinations** (un service, pas un dashboard).
- **Reçoit** : gare de départ, centres d'intérêt (nature, culture, plage,
  patrimoine, gastronomie), aptitude à la marche (rayon 500 m – 2 km), durée max.
- **Traite** : pour chaque gare, croise le trajet (durée, CO₂), la météo, les
  **POIs accessibles à pied** (affinité ML), l'**affluence** (critère « calme »),
  le **CO₂ économisé vs voiture** et les **événements à venir**, puis calcule un
  score pondéré.
- **Renvoie** : un **top de destinations** + la **liste des activités à pied**
  (ex. « Lille : 412 lieux à pied, affinité 82 % »).

## 4. Données nécessaires
- **API SNCF** `/places` (résolution des gares) + `/journeys` (durée, CO₂) —
  rôle **central**.
- **Open-Meteo** (sans clé) — météo à l'arrivée.
- **DATAtourisme** (clé) — POIs labellisés tourisme (source principale) ;
  **OpenStreetMap / Overpass** (sans clé) en repli.
- **`frequentation-gares`** (SNCF) — affluence (critère « calme »).
- **`emission-co2-perimetre-complet`** (SNCF) — CO₂ économisé vs voiture.
- **OpenAgenda** (clé) — événements à venir par ville (info).

## 5. MVP réaliste (jeudi)
✅ Fonctionnel : `escapades.py` + interface Streamlit `app_reco.py` classent
15 destinations depuis une gare au choix, sur **affinité ML + météo + calme +
durée + CO₂**, avec la liste des activités à pied.

## 6. Mode dégradé prévu
Toutes les sources passent par une fonction unique avec **cache JSON local** et
repli automatique ; `RECO_CACHE_FIRST=1` sert le cache sans réseau. Échantillons
versionnés dans `exemples_json/`. La démo tourne donc hors-ligne.

## 7. Angle et différenciation
**Angle : tourisme en train sans voiture.** Différenciation = l'**accessibilité
à pied des activités** comme critère central, mesurée par une **affinité ML**
(similarité cosinus entre les centres d'intérêt et le profil d'activités de la
ville), complétée par l'affluence (éviter la foule). Pas une carte pour analyste,
mais un service : *« où aller en train et tout faire à pied, selon mes envies ? »*.
