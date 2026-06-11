"""
Briques Machine Learning du recommandateur.

1. Affinité content-based : chaque destination = vecteur de son profil
   d'activités (nb de POIs par catégorie), l'utilisateur = vecteur de ses
   centres d'intérêt. Affinité = **similarité cosinus** entre les deux
   → critère « activités » du score.

2. Profils de villes (k-means, non supervisé) : clustering des destinations
   par leur MIX d'activités (proportions, pas volumes — une petite ville très
   « patrimoine » rejoint les grandes villes « patrimoine »). k est choisi par
   le score de silhouette, chaque cluster est nommé d'après les catégories
   dominantes de son centroïde → reste explicable. Alimente la suggestion
   « villes au profil similaire » (alternatives au même ADN que la 1re reco).
"""
import numpy as np

from escapade.sources.poi_osm import CATEGORIES

CATS = list(CATEGORIES)

EMOJI = {"plage": "🏖️", "culture": "🎭", "patrimoine": "🏛️",
         "nature": "🌿", "gastronomie": "🍽️"}


def affinity(counts, interests):
    """Similarité cosinus [0,1] entre le profil POI d'une destination et les
    centres d'intérêt cochés (vecteur indicateur 0/1)."""
    v = np.array([counts.get(c, 0) for c in CATS], dtype=float)
    u = np.array([1.0 if c in interests else 0.0 for c in CATS], dtype=float)
    nv, nu = np.linalg.norm(v), np.linalg.norm(u)
    if nv == 0 or nu == 0:
        return 0.0
    return float(np.dot(v, u) / (nv * nu))


def _mix(counts_list):
    """Matrice (villes × catégories) en PROPORTIONS — le mix d'activités."""
    X = np.array([[c.get(cat, 0) for cat in CATS] for c in counts_list], dtype=float)
    s = X.sum(axis=1, keepdims=True)
    return np.divide(X, s, out=np.zeros_like(X), where=s > 0)


def similarity(counts_a, counts_b):
    """Similarité cosinus [0,1] entre les profils d'activités de deux villes."""
    va = np.array([counts_a.get(c, 0) for c in CATS], dtype=float)
    vb = np.array([counts_b.get(c, 0) for c in CATS], dtype=float)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def city_profiles(counts_list, k=None, random_state=42):
    """Apprend les profils de villes par k-means sur le mix d'activités.

    Le mix (proportions) est STANDARDISÉ par catégorie (z-scores) avant le
    clustering : sans cela, une catégorie omniprésente (gastronomie : les
    restaurants sont partout) écrase les catégories distinctives (plage,
    nature) et toutes les villes se ressemblent.

    Retourne (labels, noms) : labels[i] = cluster de la ville i,
    noms[cluster] = nom lisible, dérivé des catégories SUR-REPRÉSENTÉES du
    centroïde (z > 0 = au-dessus de la moyenne des villes) — explicable.
    k est choisi par silhouette sur 2..5 si non fourni ; random_state fixé
    → résultat reproductible d'une exécution à l'autre.
    """
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    n = len(counts_list)
    if n < 4:  # trop peu de villes pour des clusters significatifs
        return [0] * n, {0: "—"}
    X = StandardScaler().fit_transform(_mix(counts_list))

    if k is None:  # choix de k par silhouette (cohésion vs séparation)
        best = None
        for kk in range(2, min(5, n - 1) + 1):
            km = KMeans(n_clusters=kk, n_init=10, random_state=random_state).fit(X)
            sc = silhouette_score(X, km.labels_)
            if best is None or sc > best[0]:
                best = (sc, km)
        km = best[1]
    else:
        km = KMeans(n_clusters=k, n_init=10, random_state=random_state).fit(X)

    # nom du cluster = catégories sur-représentées de son centroïde (z > 0.25)
    noms = {}
    for c, center in enumerate(km.cluster_centers_):
        order = np.argsort(center)[::-1]
        top = [CATS[i] for i in order[:2] if center[i] >= 0.25] or [CATS[order[0]]]
        nom = " & ".join(top).capitalize()
        noms[c] = f"{EMOJI.get(top[0], '')} {nom}".strip()
    return list(km.labels_), noms
