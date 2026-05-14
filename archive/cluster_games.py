#!/usr/bin/env python3
"""
Cluster all game embeddings into N groups using K-means (spherical, since vectors are L2-normalized).
Saves cluster assignments + normalized centroids to clusters.json.

Usage: python3 archive/cluster_games.py [--k 20]

Label strategy:
  - "Indie" is excluded (distribution model, not gameplay genre)
  - TF-IDF weighting: prefer genres that are *overrepresented* in this cluster vs. the corpus
  - Steam tags aggregated per cluster to enrich display labels
  - Subgenres only used when strongly dominant (>25% of cluster) AND cluster-specific
"""
import json, struct, os, sys, time
import numpy as np
from sklearn.cluster import MiniBatchKMeans
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))

# Genres that don't describe gameplay — excluded from labels
# Sport: very broadly applied in IGDB (includes casual/party games), rarely discriminative
LABEL_NOISE = {'Indie', 'Arcade', 'Sport'}

# Steam tags that are too generic to use as secondary labels
STEAM_NOISE = {
    'Singleplayer', 'Multiplayer', 'Action', 'Adventure', 'Local Multiplayer',
    'Co-op', 'Online Co-op', 'Early Access', 'Free to Play', 'Family Friendly',
    'Controller', '2D', '3D', 'Indie',
    # Genre duplicates (already captured by the IGDB genre primary label)
    'Platformer', 'Shooter', 'RPG', 'Fighting', 'Racing', 'Sports',
    'Simulation', 'Strategy', 'Puzzle',
    # Mood/aesthetic tags — fine to show in pills but not as genre labels
    'Great Soundtrack', 'Funny', 'Cute', 'Colorful', 'Difficult', 'Gore',
    'Dark', 'Violent', 'Comedy', 'Horror', 'NSFW',
}

# Genre name normalisation for display
GENRE_SHORT = {
    'Role-playing (RPG)':                'RPG',
    "Hack and slash/Beat 'em up":        'Hack & Slash',
    'Real Time Strategy (RTS)':          'RTS',
    'Turn-based strategy (TBS)':         'TBS',
    'Point-and-click':                   'Point & Click',
    'Card & Board Game':                 'Card / Board',
    'Quiz/Trivia':                       'Trivia',
    'Visual Novel':                      'Visual Novel',
}

def shorten(g):
    return GENRE_SHORT.get(g, g)

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

def tfidf_top(cluster_counter, global_counter, n_cluster, n_total, n=3, exclude=None):
    """
    Return top-n genres for this cluster weighted by how cluster-specific they are.
    Score = (cluster_freq) * log((1 + global_freq)^-1 * n_total + 1)
    (simplified TF-IDF: high cluster prevalence × low overall prevalence)
    """
    exclude = exclude or set()
    scores = {}
    for genre, cnt in cluster_counter.items():
        if genre in exclude:
            continue
        cluster_freq = cnt / max(n_cluster, 1)
        global_freq  = global_counter.get(genre, 1) / max(n_total, 1)
        # Boost genres that are over-represented in this cluster
        scores[genre] = cluster_freq / (global_freq + 0.05)
    return sorted(scores, key=lambda g: -scores[g])[:n]

def top_steam_tags(cluster_igdb_ids_set, steam_all, n=5):
    """Aggregate Steam tags across all games in cluster, return top-n by vote count."""
    tag_c = Counter()
    for iid in cluster_igdb_ids_set:
        for tag in (steam_all.get(str(iid)) or []):
            tag_c[tag] += 1
    # Remove generic tags that add no meaning
    for noise in ('Indie', 'Early Access', 'Free to Play', 'Casual', 'Massively Multiplayer'):
        tag_c.pop(noise, None)
    return [t for t, _ in tag_c.most_common(n)]

def main():
    N = 20
    for i, arg in enumerate(sys.argv[1:]):
        if arg == '--k' and i + 1 < len(sys.argv[1:]):
            N = int(sys.argv[i + 2])

    print("Loading embeddings...", flush=True)
    t0 = time.time()
    igdb_ids, vectors = load_embeddings()
    print(f"  {len(igdb_ids)} games, {vectors.shape[1]} dims  ({time.time()-t0:.1f}s)")

    print("Loading backlog...", flush=True)
    backlog  = json.load(open(os.path.join(BASE, '..', 'backlog.json')))
    id_map   = {g['igdb_id']: g for g in backlog}

    steam_path = os.path.join(BASE, '..', 'steam_tags.json')
    steam_all  = json.load(open(steam_path)) if os.path.exists(steam_path) else {}
    print(f"  Steam tags: {len(steam_all)} entries")

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

    # ── Global genre / subgenre frequency for TF-IDF ─────────────────────────
    n_total       = len(igdb_ids)
    global_genre  = Counter()
    global_sub    = Counter()
    for g in backlog:
        for x in (g.get('genres')    or []): global_genre[x]  += 1
        for x in (g.get('subgenres') or []): global_sub[x]    += 1

    print("\nBuilding cluster metadata...", flush=True)
    assignments = {}
    clusters    = []

    for cid in range(N):
        mask             = labels == cid
        cluster_igdb_ids = igdb_ids[mask].tolist()
        n_cluster        = int(mask.sum())

        games_in = [id_map.get(int(iid)) for iid in cluster_igdb_ids]
        games_in = [g for g in games_in if g]

        # Top games by IGDB rating
        rated = sorted(
            [(g['igdb_id'], g.get('igdb_rating') or 0, g['title']) for g in games_in],
            key=lambda x: -x[1]
        )
        top_games = [{'igdb_id': r[0], 'title': r[2], 'igdb_rating': round(r[1], 1)}
                     for r in rated[:12]]

        # Genre + subgenre frequency (raw counts)
        genre_c    = Counter()
        subgenre_c = Counter()
        for g in games_in:
            for x in (g.get('genres')    or []): genre_c[x]    += 1
            for x in (g.get('subgenres') or []): subgenre_c[x] += 1

        # TF-IDF discriminative genres (excluding noise like "Indie")
        tfidf_genres = tfidf_top(genre_c, global_genre, n_cluster, n_total,
                                 n=4, exclude=LABEL_NOISE)
        # Allow Sport back as primary label if it strongly dominates this cluster
        # (>40% of games have Sport → genuine sports cluster, not noise)
        sport_pct = genre_c.get('Sport', 0) / max(n_cluster, 1)
        if sport_pct > 0.40:
            tfidf_genres = ['Sport'] + [g for g in tfidf_genres if g != 'Sport']

        # Raw top genres (for metadata, excluding noise)
        top_genres = [g for g in (g for g, _ in genre_c.most_common(8))
                      if g not in LABEL_NOISE][:5]

        # Subgenres: only show cluster-specific ones (overrepresented vs. global)
        tfidf_subs = tfidf_top(subgenre_c, global_sub, n_cluster, n_total,
                               n=4, exclude=set())
        # Filter: subgenre must cover ≥10% of the cluster to be shown
        top_subgenres = [s for s in tfidf_subs
                         if subgenre_c[s] / max(n_cluster, 1) >= 0.10]

        # Steam tags for this cluster
        cluster_ids_set = {int(iid) for iid in cluster_igdb_ids}
        steam_tags = top_steam_tags(cluster_ids_set, steam_all, n=6)

        # ── Auto-label ──────────────────────────────────────────────────────
        # Priority:
        #   1. Subgenre if strongly dominant (>30%) AND cluster-specific (rare globally)
        #   2. Primary: top TF-IDF IGDB genre (excludes Indie/Arcade/Sport)
        #   3. Secondary: either 2nd TF-IDF genre OR a descriptive Steam tag
        label_parts = []

        if top_subgenres:
            top_sub = top_subgenres[0]
            sub_pct = subgenre_c[top_sub] / max(n_cluster, 1)
            sub_global_pct = global_sub.get(top_sub, 1) / max(n_total, 1)
            if sub_pct > 0.30 and sub_pct > sub_global_pct * 1.5:
                label_parts.append(top_sub.title())

        # Primary genre
        for g in tfidf_genres[:1]:
            sg = shorten(g)
            if sg not in label_parts:
                label_parts.append(sg)

        # Secondary: try descriptive Steam tag first (usually richer than 2nd IGDB genre),
        # then fall back to 2nd TF-IDF genre
        if len(label_parts) < 2:
            for tag in steam_tags:
                if tag not in STEAM_NOISE and tag not in label_parts:
                    label_parts.append(tag)
                    break

        if len(label_parts) < 2:
            for g in tfidf_genres[1:3]:
                sg = shorten(g)
                if sg not in label_parts:
                    label_parts.append(sg)
                    break

        if not label_parts:
            label_parts = [shorten(g) for g in top_genres[:2]]

        label = ' / '.join(label_parts[:2]) or f'Cluster {cid}'

        clusters.append({
            'id':            cid,
            'size':          n_cluster,
            'centroid':      [round(float(x), 6) for x in centroids[cid]],
            'top_games':     top_games,
            'top_genres':    top_genres,
            'top_subgenres': top_subgenres,
            'steam_tags':    steam_tags,
            'label':         label,
        })

        for iid in cluster_igdb_ids:
            assignments[str(int(iid))] = cid

    # Sort clusters by size
    clusters.sort(key=lambda x: -x['size'])

    result = {
        'n_clusters':  N,
        'clusters':    clusters,
        'assignments': assignments,
    }

    out = os.path.join(BASE, '..', 'clusters.json')
    with open(out, 'w') as f:
        json.dump(result, f, separators=(',', ':'))

    size_kb = os.path.getsize(out) / 1024
    print(f"\nSaved {out}  ({size_kb:.0f} KB)", flush=True)

    print(f"\n{'ID':>3}  {'Size':>5}  {'Label':<28}  {'Steam tags':<40}  Top 3 games")
    print("─" * 120)
    for c in clusters:
        games_str = ', '.join(g['title'] for g in c['top_games'][:3])
        tags_str  = ', '.join(c.get('steam_tags', [])[:3])
        print(f"{c['id']:>3}  {c['size']:>5}  {c['label']:<28}  {tags_str:<40}  {games_str}")

    bp = next((g for g in backlog if 'blue prince' in g['title'].lower()), None)
    tw = next((g for g in backlog if g['title'].lower() == 'the witness'), None)
    if bp and tw:
        bp_c = assignments.get(str(bp['igdb_id']), '?')
        tw_c = assignments.get(str(tw['igdb_id']), '?')
        same = "✓ SAME CLUSTER" if bp_c == tw_c else f"✗ different  ({bp_c} vs {tw_c})"
        print(f"\nBlue Prince → cluster {bp_c}")
        print(f"The Witness  → cluster {tw_c}   {same}")

    print("\nDone.")

if __name__ == '__main__':
    main()
