#!/usr/bin/env python3
"""Fetch RAWG IDs for games in games.json that don't have one."""
import json, time, urllib.request, urllib.parse, difflib, sys

API_KEY = 'RAWG_API_KEY'  # set in .env
DELAY   = 0.35  # seconds between requests


def search_rawg(title):
    params = urllib.parse.urlencode({
        'key': API_KEY,
        'search': title,
        'page_size': 3,
    })
    url = f'https://api.rawg.io/api/games?{params}'
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.load(r)
        return data.get('results', [])
    except Exception as e:
        print(f'  [ERROR] {e}')
        return []


def similarity(a, b):
    return difflib.SequenceMatcher(None, a.lower(), b.lower()).ratio()


def best_match(title, results):
    for r in results:
        s = similarity(title, r['name'])
        if s >= 0.80:
            return r['id'], r['name'], s
    return None, None, 0.0


def main():
    with open('games.json') as f:
        data = json.load(f)

    games   = data['games']
    missing = [g for g in games if not g.get('rawg_id')]
    total   = len(missing)
    found   = 0
    skipped = 0

    print(f'Fetching RAWG IDs for {total} games...')

    for i, g in enumerate(missing, 1):
        title   = g['title']
        results = search_rawg(title)

        if results:
            rid, matched_name, score = best_match(title, results)
            if rid:
                g['rawg_id'] = rid
                found += 1
                print(f'[{i}/{total}] ✓ {title!r} → {rid} ({matched_name!r}, {score:.2f})')
            else:
                skipped += 1
                best = results[0]['name'] if results else '?'
                print(f'[{i}/{total}] ~ {title!r} → no match (best: {best!r})')
        else:
            skipped += 1
            print(f'[{i}/{total}] ✗ {title!r} → no results')

        time.sleep(DELAY)

    with open('games.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'\nDone. Found: {found}/{total}, skipped/no-match: {skipped}')

    # Sync to server
    import urllib.request as req
    payload = json.dumps(data).encode()
    r = req.Request('http://localhost:7432/games.json', data=payload,
                    headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with req.urlopen(r, timeout=5) as resp:
            print(f'Synced to server: {resp.read()}')
    except Exception as e:
        print(f'Server sync failed (not running?): {e}')


if __name__ == '__main__':
    main()
