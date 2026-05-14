#!/usr/bin/env python3
"""
Fetches rich metadata from IGDB for all games in backlog.json.
Output: backlog_meta.json  —  { igdb_id: { summary, storyline, themes, keywords, player_perspectives } }

Resumable: skips games already in the output file.
"""
import json, urllib.request, time, sys, os

CLIENT_ID = '51t2iutyk6520ivmqxrlbkqyahcyge'
TOKEN     = 'khj0km4mucn1moguu5tjkqdyeperuy'

BACKLOG_PATH = os.path.join(os.path.dirname(__file__), '..', 'backlog.json')
OUT_PATH     = os.path.join(os.path.dirname(__file__), '..', 'backlog_meta.json')
CHUNK        = 500
DELAY        = 0.26   # ~4 req/s IGDB limit

FIELDS = 'summary, storyline, themes.name, keywords.name, player_perspectives.name'

def igdb_post(body):
    req = urllib.request.Request(
        'https://api.igdb.com/v4/games',
        data=body.encode(),
        headers={
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': 'text/plain',
        }
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def fetch_chunk(ids):
    ids_str = ','.join(str(i) for i in ids)
    return igdb_post(f'fields {FIELDS}; where id = ({ids_str}); limit {CHUNK};')

def main():
    backlog = json.load(open(BACKLOG_PATH))
    all_ids = [g['igdb_id'] for g in backlog]
    print(f'{len(all_ids)} games in backlog.json')

    # Load existing progress
    if os.path.exists(OUT_PATH):
        meta = json.load(open(OUT_PATH))
        print(f'Resuming — {len(meta)} already fetched')
    else:
        meta = {}

    remaining = [i for i in all_ids if str(i) not in meta]
    print(f'{len(remaining)} to fetch')

    total_chunks = (len(remaining) + CHUNK - 1) // CHUNK
    fetched = 0
    errors  = 0

    for ci, start in enumerate(range(0, len(remaining), CHUNK)):
        chunk = remaining[start:start + CHUNK]
        try:
            results = fetch_chunk(chunk)
            for g in results:
                meta[str(g['id'])] = {
                    'summary':   g.get('summary', ''),
                    'storyline': g.get('storyline', ''),
                    'themes':    [t['name'] for t in g.get('themes', [])],
                    'keywords':  [k['name'] for k in g.get('keywords', [])],
                    'perspectives': [p['name'] for p in g.get('player_perspectives', [])],
                }
            fetched += len(results)
            print(f'  chunk {ci+1}/{total_chunks} — +{len(results)} games — total stored: {len(meta)}', flush=True)
        except Exception as e:
            errors += 1
            print(f'  chunk {ci+1} ERROR: {e}', file=sys.stderr)
            time.sleep(2)

        # Save every 10 chunks (~5000 games)
        if (ci + 1) % 10 == 0:
            json.dump(meta, open(OUT_PATH, 'w'), ensure_ascii=False)
            print(f'  💾 checkpoint saved ({len(meta)} games)')

        time.sleep(DELAY)

    # Final save
    json.dump(meta, open(OUT_PATH, 'w'), ensure_ascii=False)
    print(f'\nDone. {len(meta)} games saved to backlog_meta.json ({errors} chunk errors)')

if __name__ == '__main__':
    main()
