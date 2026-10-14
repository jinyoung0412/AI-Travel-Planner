"""Optional deterministic geographic diagnostics; routes do not depend on clusters."""
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


def find_optimal_clusters(coords, max_k, seed=0):
    coords = np.asarray(coords, dtype=float)
    unique = len(np.unique(coords, axis=0))
    upper = min(max_k, unique, len(coords) - 1)
    if upper < 2:
        return 1
    best_k, best_score = 1, -1.0
    for k in range(2, upper + 1):
        labels = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(coords)
        if not 1 < len(np.unique(labels)) < len(coords):
            continue
        try:
            score = silhouette_score(coords, labels, sample_size=min(500, len(coords)), random_state=seed)
        except ValueError:  # a sampled subset may contain just one label
            continue
        if score > best_score:
            best_k, best_score = k, score
    return best_k


def perform_clustering(df, transport='대중교통', seed=0):
    result = df.copy()
    result['Cluster'] = -1
    if result.empty:
        return result
    coords = result[['latitude', 'longitude']].apply(lambda s: pd.to_numeric(s, errors='coerce'))
    valid = np.isfinite(coords).all(axis=1)
    points = coords.loc[valid].values
    if not len(points):
        return result
    max_k = min(15, max(2, int(len(points)**0.5) // (3 if transport == '대중교통' else 1)))
    k = find_optimal_clusters(points, max_k, seed) if len(points) >= 5 else 1
    result.loc[valid, 'Cluster'] = KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(points)
    return result
