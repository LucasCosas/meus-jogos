#!/usr/bin/env python3
"""
Fetches Steam community tags for all games in backlog.json.

Phase 1: SteamSpy /all  → paginated Steam catalog (name → appid, 1000/page)
Phase 2: Title match    → match backlog games to Steam appids
Phase 3: SteamSpy /appdetails → per-game tags

Output: steam_tags.json  { str(igdb_id): ["tag1", "tag2", ...] }
Resumable: skips igdb_ids already in output file.

Run: python3 archive/fetch_steam_tags.py
"""
import json, urllib.request, time, os, re, sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE        = os.path.dirname(os.path.abspath(__file__))
BACKLOG     = os.path.join(BASE, '..', 'backlog.json')
STEAM_CACHE = os.path.join(BASE, '..', 'steam_applist.json')   # local cache
OUT         = os.path.join(BASE, '..', 'steam_tags.json')
SPY_WORKERS = 5
SPY_DELAY   = 0.35
SAVE_EVERY  = 300

def norm(s):
    return re.sub(r'[^a-z0-9]', '', s.lower())

def spy_get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)

def fetch_spy_tags(steam_id):
    try:
        data = spy_get(f'https://steamspy.com/api.php?request=appdetails&appid={steam_id}')
        tags = data.get('tags') or {}
        if isinstance(tags, dict):
            return [t for t, _ in sorted(tags.items(), key=lambda x: -x[1])[:20]]
        return []
    except Exception:
        return []

# ── Phase 1: Build Steam name → appid index ───────────────────────────────────
def load_steam_catalog():
    if os.path.exists(STEAM_CACHE):
        data = json.load(open(STEAM_CACHE))
        print(f'  Loaded from cache: {len(data)} apps')
        return data   # {norm_name: appid}

    print('  Fetching from SteamSpy (paginated, ~3-5 min)...')
    catalog = {}   # norm_name → appid
    page    = 0
    while True:
        try:
            data = spy_get(f'https://steamspy.com/api.php?request=all&page={page}')
        except Exception as e:
            print(f'  Page {page} error: {e}')
            break
        if not data:
            break
        for appid_str, app in data.items():
            name = app.get('name', '')
            n    = norm(name)
            if n and n not in catalog:
                catalog[n] = int(appid_str)
        page += 1
        if page % 20 == 0:
            print(f'  {page} pages done  ({len(catalog)} apps)', flush=True)
        time.sleep(0.6)
        # SteamSpy paginates ~100-200 pages; empty page = done
        if len(data) < 1000:
            break

    with open(STEAM_CACHE, 'w') as f:
        json.dump(catalog, f, separators=(',', ':'))
    print(f'  Cached: {len(catalog)} Steam apps')
    return catalog

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    backlog = json.load(open(BACKLOG))
    print(f'{len(backlog)} games in backlog.json')

    result = {}
    if os.path.exists(OUT):
        result = json.load(open(OUT))
        print(f'Resuming: {len(result)} already done')

    need = [g for g in backlog if str(g['igdb_id']) not in result]
    print(f'Remaining: {len(need)} games')
    if not need:
        print('All done!')
        return

    # ── Phase 1 ──────────────────────────────────────────────────────────────
    print('\nPhase 1: Steam catalog...')
    catalog = load_steam_catalog()   # norm_name → appid
    all_norms = list(catalog.keys())

    # ── Phase 2: Match ────────────────────────────────────────────────────────
    print('\nPhase 2: matching titles...')
    igdb_to_steam = {}

    for g in need:
        title  = g['title']
        n      = norm(title)

        # Exact
        if n in catalog:
            igdb_to_steam[g['igdb_id']] = catalog[n]
            continue

        # Starts-with (handle "Game: Subtitle" vs "Game")
        sw = [t for t in all_norms if t.startswith(n[:max(len(n)-2, 4)]) and abs(len(t)-len(n)) <= 8]
        if sw:
            best = min(sw, key=lambda t: abs(len(t)-len(n)))
            igdb_to_steam[g['igdb_id']] = catalog[best]
            continue

        # No match → mark empty (PSN/Nintendo exclusives etc.)
        result[str(g['igdb_id'])] = []

    to_fetch = list(igdb_to_steam.items())
    pct = len(to_fetch) / max(len(need), 1) * 100
    print(f'  Matched: {len(to_fetch)}/{len(need)} ({pct:.0f}%)')
    print(f'  No match (exclusives etc.): {len(need) - len(to_fetch)}')

    # ── Phase 3: SteamSpy tags ────────────────────────────────────────────────
    total = len(to_fetch)
    done  = 0
    print(f'\nPhase 3: SteamSpy tags for {total} games ({SPY_WORKERS} workers)...')

    def worker(item):
        igdb_id, steam_id = item
        time.sleep(SPY_DELAY)
        return str(igdb_id), fetch_spy_tags(steam_id)

    save_ctr = 0
    with ThreadPoolExecutor(max_workers=SPY_WORKERS) as pool:
        futs = {pool.submit(worker, item): item for item in to_fetch}
        for fut in as_completed(futs):
            key, tags = fut.result()
            result[key] = tags
            done     += 1
            save_ctr += 1
            if save_ctr >= SAVE_EVERY:
                with open(OUT, 'w') as f:
                    json.dump(result, f, separators=(',', ':'))
                save_ctr = 0
            if done % 500 == 0 or done == total:
                with_tags = sum(1 for v in result.values() if v)
                print(f'  {done}/{total} ({done/total*100:.0f}%)  with_tags={with_tags}')

    with open(OUT, 'w') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))

    with_tags = sum(1 for v in result.values() if v)
    size_kb   = os.path.getsize(OUT) / 1024
    print(f'\nDone! {len(result)} entries, {with_tags} with Steam tags  ({size_kb:.0f} KB)')

    print('\nSanity check:')
    for title in ['Blue Prince', 'The Witness', 'Hollow Knight', 'Elden Ring', 'Celeste']:
        g    = next((x for x in backlog if x['title'].lower() == title.lower()), None)
        if g:
            tags = result.get(str(g['igdb_id']), [])
            print(f'  {title:<25} {tags[:8]}')

if __name__ == '__main__':
    main()
