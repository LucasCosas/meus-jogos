#!/usr/bin/env python3
"""
Generates semantic embeddings for all games in backlog.json.

Data sources (in priority order):
  1. enriched_descriptions.json  — LLM-generated vibe descriptions (best)
  2. steam_tags.json             — Steam community tags (great signal)
  3. wiki_summaries.json         — Wikipedia intro text (good signal)
  4. backlog_meta.json           — IGDB themes/keywords/summary (baseline)

Output: embeddings.bin
  [n_games: uint32]
  for each game: [igdb_id: uint32][vector: float32 × 384]

Model: all-MiniLM-L6-v2 (80MB, 384 dims, runs on CPU/MPS)
"""
import json, struct, os, time, sys
import numpy as np
from sentence_transformers import SentenceTransformer

BASE      = os.path.dirname(os.path.abspath(__file__))
ROOT      = os.path.join(BASE, '..')
DATA      = os.path.join(BASE, '..', 'data')
BACKLOG   = os.path.join(ROOT, 'backlog.json')
META      = os.path.join(DATA, 'backlog_meta.json')
STEAM     = os.path.join(DATA, 'steam_tags.json')
WIKI      = os.path.join(DATA, 'wiki_summaries.json')
ENRICHED  = os.path.join(DATA, 'enriched_descriptions.json')
OUT       = os.path.join(ROOT, 'embeddings.bin')
MODEL     = 'all-MiniLM-L6-v2'
BATCH     = 256

def build_text(game, meta, steam_tags=None, wiki=None, enriched=None):
    """
    Build the richest possible text for embedding.

    If an LLM-generated description exists, use it as the primary text
    and append Steam tags + IGDB genres as context.

    Otherwise fall back to structured metadata (IGDB + Steam + Wikipedia).

    Title is intentionally excluded — it's an identifier, not a descriptor.
    """
    igdb_id = str(game['igdb_id'])
    st      = (steam_tags or {}).get(igdb_id) or []
    wiki_t  = ((wiki or {}).get(igdb_id) or '').strip()
    enr     = ((enriched or {}).get(igdb_id) or '').strip()

    # ── Path A: LLM description available ────────────────────────────────────
    if enr:
        parts = [enr]
        if st:
            parts.append('Steam tags: ' + ', '.join(st[:15]))
        genres = game.get('genres') or []
        if genres:
            parts.append('Genres: ' + ', '.join(genres))
        return '. '.join(parts)

    # ── Path B: Structured metadata ───────────────────────────────────────────
    parts = []

    genres = game.get('genres') or []
    if genres:
        parts.append('Genres: ' + ', '.join(genres))

    if st:
        parts.append('Steam tags: ' + ', '.join(st[:20]))

    themes = meta.get('themes') or []
    if themes:
        parts.append('Themes: ' + ', '.join(themes))

    persp = meta.get('perspectives') or []
    if persp:
        parts.append('Perspective: ' + ', '.join(persp))

    kws = meta.get('keywords') or []
    if kws:
        parts.append('IGDB tags: ' + ', '.join(kws[:30]))

    if wiki_t:
        parts.append(wiki_t[:500])

    summary = (meta.get('summary') or '').strip()
    if summary:
        parts.append(summary)

    storyline = (meta.get('storyline') or '').strip()
    if storyline and storyline != summary:
        parts.append(storyline)

    return '. '.join(parts)

def main():
    print('Loading data...')
    backlog  = json.load(open(BACKLOG))
    meta     = json.load(open(META))
    steam    = json.load(open(STEAM))    if os.path.exists(STEAM)    else {}
    wiki     = json.load(open(WIKI))     if os.path.exists(WIKI)     else {}
    enriched = json.load(open(ENRICHED)) if os.path.exists(ENRICHED) else {}

    n_steam    = sum(1 for v in steam.values()    if v)
    n_wiki     = sum(1 for v in wiki.values()     if v)
    n_enriched = sum(1 for v in enriched.values() if v)
    print(f'  {len(backlog)} games in backlog.json')
    print(f'  {len(meta)} IGDB metadata entries')
    print(f'  {n_steam} Steam tag sets  |  {n_wiki} Wikipedia summaries  |  {n_enriched} LLM descriptions')

    print(f'\nLoading model {MODEL}...')
    t0 = time.time()
    model = SentenceTransformer(MODEL)
    print(f'  Ready in {time.time()-t0:.1f}s')

    # Build (igdb_id, text) pairs — skip games with no usable text
    games_data = []
    skipped    = 0
    src_counts = {'enriched': 0, 'structured': 0}
    for g in backlog:
        igdb_id = g['igdb_id']
        m       = meta.get(str(igdb_id), {})
        enr     = (enriched.get(str(igdb_id)) or '').strip()
        text    = build_text(g, m, steam, wiki, enriched)
        if not text.strip():
            skipped += 1
            continue
        src_counts['enriched' if enr else 'structured'] += 1
        games_data.append((igdb_id, text))
    if skipped:
        print(f'  Skipped {skipped} games with no text')
    print(f'  Using LLM descriptions: {src_counts["enriched"]}  |  structured fallback: {src_counts["structured"]}')

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
