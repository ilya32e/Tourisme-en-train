# Axes de réflexion guidée

*EFREI Paris · Learning XP « Tourisme en train » · 8–12 juin 2026*

Quatre angles pour explorer le projet avant de converger vers l'idée finale.

## ① Par PERSONA — à qui on s'adresse

| Persona | Besoin | Idée de service |
|---|---|---|
| Étudiant sans voiture | Partir pas cher, vite | Escapade TGVmax au meilleur prix |
| Famille avec poussette | Gares accessibles | Trajet « sans galère » (ascenseurs, PMR) |
| Couple en week-end | Une parenthèse sympa | Escapade météo (angle retenu) |
| Touriste étranger | Découvrir hors Paris | Itinéraire culturel + événements |

## ② Par MOMENT du voyage — avant / pendant / après

- **Avant** : choisir où et quand partir → c'est là que se joue notre service.
- **Pendant** : suivre les départs, retards, correspondances (`/departures`, `/disruptions`).
- **Après** : récap du voyage, CO₂ économisé vs voiture, partage.

## ③ Par PAIN POINT — les irritants à résoudre

- « Je ne sais pas où aller ce week-end. » → recommandation.
- « Je suis parti et il pleuvait. » → météo à l'arrivée (angle retenu).
- « La gare n'était pas accessible. » → filtre PMR.
- « Trop cher ou complet. » → TGVmax.
- « Train supprimé, je l'ai su trop tard. » → alertes temps réel.

## ④ Par DONNÉES disponibles — ce que le data permet

| Donnée | Ce qu'elle débloque |
|---|---|
| `/journeys` (durée, CO₂) | comparer et classer des trajets |
| Open-Meteo | météo à destination (angle retenu) |
| `frequentation-gares` | éviter l'affluence |
| `equipements-accessibilite-sncf` | filtre PMR |
| `tgvmax` | angle prix jeune |
| OpenAgenda / DATAtourisme | événements et points d'intérêt |

---

## Synthèse — vers l'idée finale

Les quatre axes convergent vers l'angle choisi :

- **Persona** : couple / jeune en week-end.
- **Moment** : *avant* le voyage (la décision).
- **Pain point** : « parti sous la pluie ».
- **Données** : `/journeys` + Open-Meteo, déjà branchés et fonctionnels.

**Idée finale retenue :** un service « Où et quand partir en train ce week-end ? »
qui croise trajet SNCF (durée, CO₂) et météo à l'arrivée pour recommander la
meilleure escapade.
