#!/usr/bin/env python3
"""
Fetches Wikipedia intro summaries — single-threaded, action API only.
0.5s delay per API call. On 429: reads Retry-After header and waits.

Strategy per game:
  1. Try "{title} (video game)"
  2. Try "{title}"
  3. Search "{title} video game" → try found title

Estimated time: ~2-3h for 13k games (0.5s/call, avg 1.5 calls/game)

Run: python3 scripts/fetch_wiki_single.py
"""
import json, urllib.request, urllib.parse, urllib.error, time, os, socket

BASE    = os.path.dirname(os.path.abspath(__file__))
ROOT    = os.path.join(BASE, '..')
DATA    = os.path.join(BASE, '..', 'data')
BACKLOG = os.path.join(ROOT, 'backlog.json')
OUT     = os.path.join(DATA, 'wiki_summaries.json')

DELAY      = 0.5    # seconds between every API call
SAVE_EVERY = 200
UA         = 'GameRecommender/1.0 (personal project; contact: none)'

def wiki_api(**params):
    """Call MediaWiki action API. Returns parsed JSON or {}. Handles 429 with Retry-After."""
    time.sleep(DELAY)
    params['format'] = 'json'
    url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                retry_after = int(e.headers.get('Retry-After', 10))
                wait = retry_after + 2
                print(f'    Rate limited (HTTP {e.code}), waiting {wait}s...', flush=True)
                time.sleep(wait)
            else:
                return {}
        except Exception:
            time.sleep(2)
    return {}

def get_extract(title):
    data = wiki_api(
        action='query',
        titles=title,
        prop='extracts',
        exintro=1,
        exsentences=5,
        explaintext=1,
        redirects=1,
    )
    pages = data.get('query', {}).get('pages', {})
    for pid, page in pages.items():
        if pid == '-1':
            return None
        extract = (page.get('extract') or '').strip()
        if not extract:
            return None
        if 'may refer to' in extract[:150] or 'disambiguation' in extract[:150].lower():
            return None
        return extract
    return None

def search_wiki(query):
    data = wiki_api(
        action='query',
        list='search',
        srsearch=query,
        srlimit=3,
        srnamespace=0,
    )
    hits = data.get('query', {}).get('search', [])
    for hit in hits:
        t = hit.get('title', '')
        if any(kw in t.lower() for kw in ['video game', 'game', '(series)']):
            return t
    return hits[0]['title'] if hits else None

def fetch_for_game(game):
    title = game['title']
    year  = game.get('year')

    ext = get_extract(f'{title} (video game)')
    if ext:
        return ext

    ext = get_extract(title)
    if ext:
        return ext

    query = f'{title} {year} video game' if year else f'{title} video game'
    found = search_wiki(query)
    if found:
        ext = get_extract(found)
        if ext:
            return ext

    return ''

def main():
    backlog = json.load(open(BACKLOG))
    print(f'{len(backlog)} games in backlog.json')

    result = {}
    if os.path.exists(OUT):
        result = json.load(open(OUT))
        print(f'Resuming: {len(result)} already done')

    need = [g for g in backlog if str(g['igdb_id']) not in result]
    est  = len(need) * DELAY * 1.5 / 60
    print(f'Remaining: {len(need)} games  (~{est:.0f} min estimated)')

    if not need:
        print('All done!')
        return

    total    = len(need)
    done     = 0
    save_ctr = 0
    found    = 0
    t_start  = time.time()

    for game in need:
        key  = str(game['igdb_id'])
        text = fetch_for_game(game)
        result[key] = text
        done     += 1
        save_ctr += 1
        if text:
            found += 1

        if save_ctr >= SAVE_EVERY:
            with open(OUT, 'w') as f:
                json.dump(result, f, ensure_ascii=False, separators=(',', ':'))
            save_ctr = 0

        if done % 500 == 0 or done == total:
            elapsed = time.time() - t_start
            rate    = done / max(elapsed, 1)
            eta_min = (total - done) / rate / 60
            pct     = done / total * 100
            print(f'  {done}/{total} ({pct:.0f}%)  found={found}  miss={done-found}  ETA={eta_min:.0f}min', flush=True)

    with open(OUT, 'w') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))

    with_text = sum(1 for v in result.values() if v)
    size_kb   = os.path.getsize(OUT) / 1024
    print(f'\nDone! {len(result)} entries, {with_text} with text ({with_text/len(result)*100:.0f}%)  ({size_kb:.0f} KB)')

    print('\nSanity check:')
    for title in ['Blue Prince', 'The Witness', 'Hollow Knight', 'Elden Ring', 'Celeste', 'Hades']:
        g = next((x for x in backlog if x['title'].lower() == title.lower()), None)
        if g:
            text = result.get(str(g['igdb_id']), '')
            snippet = text[:120].replace('\n', ' ') if text else '(not found)'
            print(f'  {title:<25} {snippet}')

if __name__ == '__main__':
    main()
