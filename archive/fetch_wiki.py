#!/usr/bin/env python3
"""
Fetches Wikipedia intro summaries for all games in backlog.json.

Strategy per game:
  1. Try "{title} (video game)" directly
  2. Try "{title}" directly
  3. Fall back to Wikipedia search: "{title} video game"
  4. If still nothing or disambiguation → mark as empty

Output: wiki_summaries.json  { str(igdb_id): "intro text..." }
Resumable. ~15-25 min for 13k games with 12 workers.

Run: python3 archive/fetch_wiki.py
"""
import json, urllib.request, urllib.parse, time, os, re, html
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE    = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.join(BASE, '..', 'backlog.json')
OUT     = os.path.join(BASE, '..', 'wiki_summaries.json')

WORKERS    = 3
DELAY      = 1.0     # per worker — ~3 req/s total, conservative for Wikipedia
SAVE_EVERY = 500
UA         = 'GameRecommender/1.0 (personal project; contact: none)'

# ── Wikipedia API helpers ─────────────────────────────────────────────────────
def wiki_api(**params):
    params['format'] = 'json'
    url = 'https://en.wikipedia.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(5 * (attempt + 1))   # backoff: 5s, 10s, 15s, 20s
            else:
                raise
    return {}

def get_extract(title):
    """Fetch plain-text intro (≤5 sentences) for an exact Wikipedia title."""
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
        if pid == '-1':   # not found
            return None
        extract = (page.get('extract') or '').strip()
        if not extract:
            return None
        # Skip disambiguation pages
        if 'may refer to' in extract[:120] or 'disambiguation' in extract[:120].lower():
            return None
        return extract
    return None

def search_wiki(query):
    """Return best matching Wikipedia page title via search."""
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
        # Prefer results that look like video game pages
        if any(kw in t.lower() for kw in ['video game', 'game', '(series)']):
            return t
    return hits[0]['title'] if hits else None

def fetch_wiki_for_game(game):
    """Try multiple strategies to get a Wikipedia extract. Returns str or ''."""
    title = game['title']
    year  = game.get('year')

    # Strategy 1: exact "(video game)" disambiguation page
    ext = get_extract(f'{title} (video game)')
    if ext:
        return ext

    # Strategy 2: exact title (many games don't have the disambiguation suffix)
    ext = get_extract(title)
    if ext:
        return ext

    # Strategy 3: search
    query = f'{title} {year} video game' if year else f'{title} video game'
    found = search_wiki(query)
    if found:
        ext = get_extract(found)
        if ext:
            return ext

    return ''

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    backlog = json.load(open(BACKLOG))
    print(f'{len(backlog)} games in backlog.json')

    result = {}
    if os.path.exists(OUT):
        result = json.load(open(OUT))
        print(f'Resuming: {len(result)} already done')

    need = [g for g in backlog if str(g['igdb_id']) not in result]
    print(f'Remaining: {len(need)} games  ({WORKERS} workers)')

    if not need:
        print('All done!')
        return

    total    = len(need)
    done     = 0
    save_ctr = 0
    found    = 0

    def worker(game):
        time.sleep(DELAY)
        return str(game['igdb_id']), fetch_wiki_for_game(game)

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = {pool.submit(worker, g): g for g in need}
        for fut in as_completed(futs):
            key, text = fut.result()
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
                pct = done / total * 100
                print(f'  {done}/{total} ({pct:.0f}%)  found={found}  miss={done-found}', flush=True)

    with open(OUT, 'w') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))

    with_text = sum(1 for v in result.values() if v)
    size_kb   = os.path.getsize(OUT) / 1024
    print(f'\nDone! {len(result)} entries, {with_text} with text ({with_text/len(result)*100:.0f}%)  ({size_kb:.0f} KB)')

    print('\nSanity check:')
    for title in ['Blue Prince', 'The Witness', 'Hollow Knight', 'Elden Ring', 'Celeste', 'God of War']:
        g = next((x for x in backlog if x['title'].lower() == title.lower()), None)
        if g:
            text = result.get(str(g['igdb_id']), '')
            snippet = text[:120].replace('\n', ' ') if text else '(not found)'
            print(f'  {title:<25} {snippet}...')

if __name__ == '__main__':
    main()
