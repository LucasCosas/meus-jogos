#!/usr/bin/env python3
"""
Generates semantic embeddings for all games in backlog.json using
rich metadata from backlog_meta.json.

Output: embeddings.bin
  [n_games: uint32]
  for each game: [igdb_id: uint32][vector: float32 × 384]

Total size: ~25MB. Loaded once by the browser for cosine similarity.

Model: all-MiniLM-L6-v2 (80MB, 384 dims, runs on CPU/MPS)
"""
import json, struct, os, time, sys
import numpy as np
from sentence_transformers import SentenceTransformer

BASE      = os.path.dirname(os.path.abspath(__file__))
BACKLOG   = os.path.join(BASE, '..', 'backlog.json')
META      = os.path.join(BASE, '..', 'backlog_meta.json')
OUT       = os.path.join(BASE, '..', 'embeddings.bin')
MODEL     = 'all-MiniLM-L6-v2'
BATCH     = 256

def build_text(game, meta):
    """
    Concatenates semantic content into a single text for embedding.
    Title is intentionally excluded — it's an identifier, not a descriptor.
    Matching on title words ("Blue" in "Blue Prince") produces false positives.
    """
    parts = []

    genres = game.get('genres') or []
    if genres:
        parts.append('Genres: ' + ', '.join(genres))

    themes = meta.get('themes') or []
    if themes:
        parts.append('Themes: ' + ', '.join(themes))

    persp = meta.get('perspectives') or []
    if persp:
        parts.append('Perspective: ' + ', '.join(persp))

    kws = meta.get('keywords') or []
    if kws:
        # Cap at 40 keywords — beyond that it's noise
        parts.append('Tags: ' + ', '.join(kws[:40]))

    summary = (meta.get('summary') or '').strip()
    if summary:
        parts.append(summary)

    storyline = (meta.get('storyline') or '').strip()
    if storyline and storyline != summary:
        parts.append(storyline)

    return '. '.join(parts)

def main():
    print('Loading data...')
    backlog = json.load(open(BACKLOG))
    meta    = json.load(open(META))
    print(f'  {len(backlog)} games in backlog.json')
    print(f'  {len(meta)} entries in backlog_meta.json')

    print(f'\nLoading model {MODEL}...')
    t0 = time.time()
    model = SentenceTransformer(MODEL)
    print(f'  Ready in {time.time()-t0:.1f}s')

    # Build (igdb_id, text) pairs — skip games with no usable text
    games_data = []
    skipped = 0
    for g in backlog:
        igdb_id = g['igdb_id']
        m = meta.get(str(igdb_id), {})
        text = build_text(g, m)
        if not text.strip():
            skipped += 1
            continue
        games_data.append((igdb_id, text))
    if skipped:
        print(f'  Skipped {skipped} games with no text')

    # Sample output so you can see what goes in
    print(f'\nSample text for "{backlog[0]["title"]}":')
    print(f'  {games_data[0][1][:200]}...')

    # Encode in batches
    print(f'\nEncoding {len(games_data)} games in batches of {BATCH}...')
    texts   = [t for _, t in games_data]
    igdb_ids = [i for i, _ in games_data]

    t0 = time.time()
    vectors = model.encode(
        texts,
        batch_size=BATCH,
        show_progress_bar=True,
        normalize_embeddings=True,   # unit norm → cosine sim = dot product (faster)
        convert_to_numpy=True,
    )
    elapsed = time.time() - t0
    print(f'  Done in {elapsed:.1f}s  shape={vectors.shape}  dtype={vectors.dtype}')

    # Write binary
    # Format: [n: uint32] then per game [igdb_id: uint32][384 × float32]
    n = len(igdb_ids)
    print(f'\nWriting {OUT}...')
    with open(OUT, 'wb') as f:
        f.write(struct.pack('<I', n))
        for igdb_id, vec in zip(igdb_ids, vectors):
            f.write(struct.pack('<I', igdb_id))
            f.write(vec.astype(np.float32).tobytes())

    size_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f'  Saved: {n} games, {size_mb:.1f} MB')
    print(f'\nDone. embeddings.bin ready.')

if __name__ == '__main__':
    main()
