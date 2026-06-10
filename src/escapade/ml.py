"""
Brique Machine Learning du recommandateur — affinité content-based.

On représente chaque destination par son profil d'activités (nombre de POIs
OpenStreetMap par catégorie) et l'utilisateur par un vecteur de ses centres
d'intérêt. L'affinité = **similarité cosinus** entre les deux : elle mesure à
quel point le profil d'une destination correspond aux envies de l'utilisateur,
et sert de critère « activités » dans le score (recommandation content-based).
"""
import numpy as np

from escapade.sources.poi_osm import CATEGORIES

CATS = list(CATEGORIES)


def affinity(counts, interests):
    """Similarité cosinus [0,1] entre le profil POI d'une destination et les
    centres d'intérêt cochés (vecteur indicateur 0/1)."""
    v = np.array([counts.get(c, 0) for c in CATS], dtype=float)
    u = np.array([1.0 if c in interests else 0.0 for c in CATS], dtype=float)
    nv, nu = np.linalg.norm(v), np.linalg.norm(u)
    if nv == 0 or nu == 0:
        return 0.0
    return float(np.dot(v, u) / (nv * nu))
