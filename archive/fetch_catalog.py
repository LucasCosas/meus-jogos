#!/usr/bin/env python3
"""Fetch all RAWG games with a Metacritic score into catalog_rawg.json."""
import json, time, urllib.request, urllib.parse, sys

API_KEY   = '99b150baf5084316ad6b52204a4fb102'
OUT_FILE  = 'catalog_rawg.json'
PAGE_SIZE = 40
DELAY     = 0.25  # seconds between requests

PLATFORM_MAP = {
    'PlayStation 5': 'PS5', 'PlayStation 4': 'PS4', 'PlayStation 3': 'PS3',
    'Xbox Series S/X': 'Xbox Series', 'Xbox One': 'Xbox One', 'Xbox 360': 'Xbox 360',
    'Nintendo Switch': 'Switch', 'PC': 'PC', 'macOS': 'Mac', 'iOS': 'iOS',
    'Android': 'Android', 'PlayStation': 'PS1', 'PlayStation 2': 'PS2',
}

def fetch_page(page):
    params = urllib.parse.urlencode({
        'key':        API_KEY,
        'metacritic': '1,100',
        'ordering':   '-metacritic',
        'page_size':  PAGE_SIZE,
        'page':       page,
    })
    url = f'https://api.rawg.io/api/games?{params}'
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.load(r)

def map_platforms(raw):
    out = []
    for p in (raw or []):
        name = p.get('platform', {}).get('name', '')
        mapped = PLATFORM_MAP.get(name)
        if mapped and mapped not in out:
            out.append(mapped)
    return out

def map_genres(raw):
    return [g['name'] for g in (raw or [])]

def main():
    # Get total count first
    first = fetch_page(1)
    total = first['count']
    pages = (total // PAGE_SIZE) + (1 if total % PAGE_SIZE else 0)
    print(f'{total} jogos, {pages} páginas')

    games = []

    def process_page(data):
        for g in data['results']:
            if not g.get('metacritic'):
                continue
            games.append({
                'rawg_id':    g['id'],
                'title':      g['name'],
                'metacritic': g['metacritic'],
                'rating':     round(g.get('rating') or 0, 1) or None,
                'released':   g.get('released'),
                'platforms':  map_platforms(g.get('platforms')),
                'genres':     map_genres(g.get('genres')),
                'image':      g.get('background_image'),
            })

    process_page(first)
    print(f'Página 1/{pages} — {len(games)} jogos', flush=True)

    for page in range(2, pages + 1):
        time.sleep(DELAY)
        try:
            data = fetch_page(page)
            process_page(data)
            print(f'Página {page}/{pages} — {len(games)} jogos', flush=True)
        except Exception as e:
            print(f'Erro na página {page}: {e}', file=sys.stderr)
            time.sleep(2)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(games, f, ensure_ascii=False, indent=2)

    print(f'\nSalvo: {OUT_FILE} ({len(games)} jogos)')

if __name__ == '__main__':
    main()
