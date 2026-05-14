#!/usr/bin/env python3
"""
Busca semântica interativa no catálogo de jogos.
Rode: python3 archive/query_search.py

Dois modos:
  query>   <texto livre>      busca semântica por descrição
  similar> <nome do jogo>     usa o vetor do jogo como referência (correto para "parecido com X")

Flags opcionais (no final da linha):
  --top N       número de resultados (padrão: 12)
  --igdb N      score IGDB mínimo (ex: --igdb 80)
  --year N      ano mínimo de lançamento (padrão: 2000)
  --coop        só jogos co-op

Exemplos:
  query>   challenging dark fantasy RPG great lore --igdb 80
  query>   relaxing cozy puzzle exploration
  similar> Blue Prince --top 15
  similar> Hollow Knight --igdb 75
  query>   co-op party game couch friends --coop --year 2015
"""
import struct, json, os, difflib
import numpy as np

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

def year_weight(year, min_year):
    """Decai suavemente pra jogos antigos. Jogos antes de min_year = 0."""
    if not year: return 0.5
    if year < min_year: return 0.0
    # Full weight from min_year+5 onwards, ramps up linearly before that
    return min(1.0, (year - min_year) / 5 + 0.3)

def find_game(name, id_map, igdb_ids, title_to_idx):
    """Fuzzy match game title → returns (igdb_id, idx, title) or None."""
    name_lower = name.lower()
    titles = list(title_to_idx.keys())
    matches = difflib.get_close_matches(name_lower, titles, n=3, cutoff=0.4)
    if not matches:
        # fallback: substring match
        matches = [t for t in titles if name_lower in t]
    if not matches:
        return None
    best = matches[0]
    idx  = title_to_idx[best]
    igdb_id = int(igdb_ids[idx])
    g = id_map[igdb_id]
    return igdb_id, idx, g['title']

def show_results(candidates, id_map, label, top_k, min_igdb, min_year, coop_only, exclude_id=None):
    print(f'\n{label}')
    print(f'{"#":<3} {"Título":<42} {"Score":>6} {"IGDB":>5} {"Ano":>5}  Tags')
    print("─" * 95)
    shown = 0
    for igdb_id, score in candidates:
        if shown >= top_k: break
        if igdb_id == exclude_id: continue
        g = id_map.get(igdb_id)
        if not g: continue
        igdb = g.get('igdb_rating') or 0
        year = g.get('year') or 0
        if min_igdb and igdb < min_igdb: continue
        if year_weight(year, min_year) == 0.0: continue
        if coop_only and not g.get('coop'): continue
        subs   = ', '.join(g.get('subgenres') or [])
        genres = ', '.join((g.get('genres') or [])[:2])
        tags   = (f'[{subs}] ' if subs else '') + genres
        print(f"{shown+1:<3} {g['title']:<42} {score:>6.3f} {igdb:>5.1f} {year:>5}  {tags}")
        shown += 1
    print()

def search_by_vec(qvec, vectors, igdb_ids, id_map, min_year, top_k, min_igdb, coop_only,
                  label, exclude_id=None):
    sims = vectors @ qvec
    # Apply year weight to raw similarity before sorting
    scores = []
    for idx in range(len(igdb_ids)):
        igdb_id = int(igdb_ids[idx])
        g = id_map.get(igdb_id)
        if not g: continue
        yw = year_weight(g.get('year'), min_year)
        if yw == 0.0: continue
        # Blend: 80% semantic sim + 20% year recency
        weighted = 0.80 * sims[idx] + 0.20 * yw
        scores.append((igdb_id, weighted))
    scores.sort(key=lambda x: -x[1])
    show_results(scores, id_map, label, top_k, min_igdb, min_year, coop_only, exclude_id)

def parse_line(line):
    parts    = line.split('--')
    text     = parts[0].strip()
    top_k    = 12
    min_igdb = 0
    min_year = 2000
    coop     = False
    for p in parts[1:]:
        p = p.strip()
        if p.startswith('top '):  top_k    = int(p.split()[1])
        if p.startswith('igdb '): min_igdb = float(p.split()[1])
        if p.startswith('year '): min_year = int(p.split()[1])
        if p == 'coop':           coop     = True
    return text, top_k, min_igdb, min_year, coop

def main():
    print("Carregando embeddings...", flush=True)
    igdb_ids, vectors = load_embeddings()

    backlog = json.load(open(os.path.join(BASE, '..', 'backlog.json')))
    id_map  = {g['igdb_id']: g for g in backlog}

    # Build lowercase title → index map for fuzzy matching
    title_to_idx = {g['title'].lower(): i
                    for i, igdb_id in enumerate(igdb_ids)
                    for g in [id_map.get(int(igdb_id))] if g}

    print("Carregando modelo...", flush=True)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print(f"Pronto! {len(igdb_ids)} jogos indexados.")
    print(__doc__)

    while True:
        try:
            raw = input("query/similar> ").strip()
            if not raw: continue

            # Detect mode
            if raw.lower().startswith('similar>'):
                line = raw[len('similar>'):].strip()
                text, top_k, min_igdb, min_year, coop = parse_line(line)
                result = find_game(text, id_map, igdb_ids, title_to_idx)
                if not result:
                    print(f'  ❌ Jogo "{text}" não encontrado no catálogo.\n')
                    continue
                igdb_id, idx, matched_title = result
                print(f'  ✓ Usando vetor de: "{matched_title}"')
                qvec = vectors[idx]
                search_by_vec(qvec, vectors, igdb_ids, id_map, min_year, top_k, min_igdb, coop,
                              label=f'🎮 Similar a "{matched_title}"', exclude_id=igdb_id)
            else:
                if raw.lower().startswith('query>'):
                    raw = raw[len('query>'):].strip()
                text, top_k, min_igdb, min_year, coop = parse_line(raw)
                qvec = model.encode([text], normalize_embeddings=True)[0]
                search_by_vec(qvec, vectors, igdb_ids, id_map, min_year, top_k, min_igdb, coop,
                              label=f'🔍 "{text}"')

        except (KeyboardInterrupt, EOFError):
            print("\nFalou!")
            break

if __name__ == '__main__':
    main()
