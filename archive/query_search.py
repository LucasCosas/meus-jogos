#!/usr/bin/env python3
"""
Busca semântica interativa no catálogo de jogos.
Rode: python3 archive/query_search.py

Flags opcionais na query:
  --top N      número de resultados (padrão: 12)
  --igdb N     score IGDB mínimo (ex: --igdb 80)
  --coop       só jogos co-op

Exemplos:
  query> challenging dark fantasy RPG great lore
  query> co-op party game couch friends --coop
  query> emotional narrative adventure --igdb 80 --top 20
  query> fast roguelite action run based
"""
import struct, json, os, sys
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

def search(query, vectors, igdb_ids, id_map, model, top_k=12, min_igdb=0, coop_only=False):
    qvec = model.encode([query], normalize_embeddings=True)[0]
    sims = vectors @ qvec
    top  = np.argsort(sims)[::-1]

    print(f'\n🔍 "{query}"')
    print(f'{"#":<3} {"Título":<42} {"Sim":>5} {"IGDB":>5}  Tags')
    print("─" * 90)
    shown = 0
    for idx in top:
        if shown >= top_k: break
        g = id_map.get(int(igdb_ids[idx]))
        if not g: continue
        if min_igdb and (g.get('igdb_rating') or 0) < min_igdb: continue
        if coop_only and not g.get('coop'): continue
        subs   = ', '.join(g.get('subgenres') or [])
        genres = ', '.join((g.get('genres') or [])[:2])
        tags   = (f'[{subs}] ' if subs else '') + genres
        igdb   = g.get('igdb_rating') or 0
        print(f"{shown+1:<3} {g['title']:<42} {sims[idx]:.3f} {igdb:>5.1f}  {tags}")
        shown += 1
    print()

def parse_line(line):
    parts    = line.split('--')
    query    = parts[0].strip()
    top_k    = 12
    min_igdb = 0
    coop     = False
    for p in parts[1:]:
        p = p.strip()
        if p.startswith('top '):  top_k    = int(p.split()[1])
        if p.startswith('igdb '): min_igdb = float(p.split()[1])
        if p == 'coop':           coop     = True
    return query, top_k, min_igdb, coop

def main():
    print("Carregando embeddings...", flush=True)
    igdb_ids, vectors = load_embeddings()

    backlog = json.load(open(os.path.join(BASE, '..', 'backlog.json')))
    id_map  = {g['igdb_id']: g for g in backlog}

    print("Carregando modelo...", flush=True)
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-MiniLM-L6-v2')

    print(f"Pronto! {len(igdb_ids)} jogos indexados.")
    print(__doc__)

    while True:
        try:
            line = input("query> ").strip()
            if not line: continue
            query, top_k, min_igdb, coop = parse_line(line)
            search(query, vectors, igdb_ids, id_map, model, top_k, min_igdb, coop)
        except (KeyboardInterrupt, EOFError):
            print("\nFalou!")
            break

if __name__ == '__main__':
    main()
