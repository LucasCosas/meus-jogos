#!/usr/bin/env python3
"""
Cluster all game embeddings into N groups using K-means (spherical, since vectors are L2-normalized).
Saves cluster assignments + normalized centroids to clusters.json.

Usage: python3 archive/cluster_games.py [--k 20]

Output: clusters.json
  {
    "n_clusters": 20,
    "clusters": [
      {
        "id": 0,
        "size": 812,
        "centroid": [384 floats],
        "top_games": [{igdb_id, title, igdb_rating}, ...],
        "top_genres": ["Action", "RPG", ...],
        "top_subgenres": ["soulslike", ...],
        "label": "Action RPG"
      }, ...
    ],
    "assignments": {"igdb_id": cluster_id, ...}   <- 16k entries ~200KB
  }
"""
import json, struct, os, sys, time
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))

def load_embeddings():
    path = os.path.join(BASE, '..', 'embeddings.bin')
    with open(path, 'rb') as f:
        n        = struct.unpack('<I', f.read(4))[0]
        igdb_ids = np.zeros(n, dtype=np.int32)
        vectors  = np.zeros((n, 384), dtype=np.float32)
        for i in range(n):
            igdb_ids[i] = struct.unpack('<I', f.read(4))[0]
            vectors[i]  = np.frombuffer(f.read(384 * 4), dtype=np.float32)
    return igdb_ids, vectors

def top_items(counter, n=5):
    return [x for x, _ in counter.most_common(n)]

def main():
    N = 20
    for arg in sys.argv[1:]:
        if arg.startswith('--k'):
            N = int(sys.argv[sys.argv.index(arg) + 1])

    print("Loading embeddings...", flush=True)
    t0 = time.time()
    igdb_ids, vectors = load_embeddings()
    print(f"  {len(igdb_ids)} games, {vectors.shape[1]} dims  ({time.time()-t0:.1f}s)")

    print("Loading backlog...", flush=True)
    backlog = json.load(open(os.path.join(BASE, '..', 'backlog.json')))
    id_map  = {g['igdb_id']: g for g in backlog}

    print(f"\nRunning MiniBatch K-means  k={N}...", flush=True)
    t0 = time.time()
    km = MiniBatchKMeans(
        n_clusters=N,
        random_state=42,
        n_init=10,
        batch_size=4096,
        max_iter=300,
    )
    labels    = km.fit_predict(vectors)
    centroids = km.cluster_centers_
    # Re-normalize centroids so dot product == cosine similarity
    norms     = np.linalg.norm(centroids, axis=1, keepdims=True)
    centroids = centroids / np.maximum(norms, 1e-9)
    print(f"  Done in {time.time()-t0:.1f}s   inertia={km.inertia_:.2f}", flush=True)

    print("\nBuilding cluster metadata...", flush=True)
    assignments = {}
    clusters    = []

    for cid in range(N):
        mask             = labels == cid
        cluster_igdb_ids = igdb_ids[mask].tolist()

        games_in = [id_map.get(int(iid)) for iid in cluster_igdb_ids]
        games_in = [g for g in games_in if g]

        # Top games by IGDB rating (need at least some rating)
        rated = sorted(
            [(g['igdb_id'], g.get('igdb_rating') or 0, g['title']) for g in games_in],
            key=lambda x: -x[1]
        )
        top_games = [{'igdb_id': r[0], 'title': r[2], 'igdb_rating': round(r[1], 1)}
                     for r in rated[:12]]

        # Genre + subgenre frequency
        genre_c    = Counter()
        subgenre_c = Counter()
        for g in games_in:
            for x in (g.get('genres')    or []): genre_c[x]    += 1
            for x in (g.get('subgenres') or []): subgenre_c[x] += 1

        top_genres    = top_items(genre_c, 5)
        top_subgenres = top_items(subgenre_c, 6)

        # Auto-label: prefer subgenre if it's dominant (>15% of cluster)
        label_parts = []
        if top_subgenres and subgenre_c[top_subgenres[0]] / max(len(games_in), 1) > 0.15:
            label_parts.append(top_subgenres[0].title())
        label_parts += [g for g in top_genres[:2] if g not in label_parts]
        label = ' / '.join(label_parts[:2]) or f'Cluster {cid}'

        clusters.append({
            'id':           cid,
            'size':         int(mask.sum()),
            'centroid':     [round(float(x), 6) for x in centroids[cid]],
            'top_games':    top_games,
            'top_genres':   top_genres,
            'top_subgenres': top_subgenres,
            'label':        label,
        })

        for iid in cluster_igdb_ids:
            assignments[str(int(iid))] = cid

    # Sort clusters by size for readability
    clusters.sort(key=lambda x: -x['size'])

    result = {
        'n_clusters': N,
        'clusters':   clusters,
        'assignments': assignments,
    }

    out = os.path.join(BASE, '..', 'clusters.json')
    with open(out, 'w') as f:
        json.dump(result, f, separators=(',', ':'))

    size_kb = os.path.getsize(out) / 1024
    print(f"\nSaved {out}  ({size_kb:.0f} KB)", flush=True)

    print(f"\n{'ID':>3}  {'Size':>5}  {'Label':<28}  Top 4 games")
    print("─" * 90)
    for c in clusters:
        games_str = ', '.join(g['title'] for g in c['top_games'][:4])
        print(f"{c['id']:>3}  {c['size']:>5}  {c['label']:<28}  {games_str}")

    # Quick sanity check: find Blue Prince and The Witness
    bp = next((g for g in backlog if 'blue prince' in g['title'].lower()), None)
    tw = next((g for g in backlog if 'witness' in g['title'].lower() and 'witness' == g['title'].lower().split()[0]), None)
    if bp and tw:
        bp_c = assignments.get(str(bp['igdb_id']), '?')
        tw_c = assignments.get(str(tw['igdb_id']), '?')
        same = "✓ SAME CLUSTER" if bp_c == tw_c else f"✗ different  ({bp_c} vs {tw_c})"
        print(f"\nBlue Prince → cluster {bp_c}")
        print(f"The Witness  → cluster {tw_c}   {same}")

    print("\nDone.")

if __name__ == '__main__':
    main()
