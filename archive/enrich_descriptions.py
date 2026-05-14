#!/usr/bin/env python3
"""
Generates vibe descriptions for all games using a local Ollama LLM.

Input:  backlog.json + backlog_meta.json + steam_tags.json + wiki_summaries.json
Output: enriched_descriptions.json  { str(igdb_id): "80-word vibe description" }

The description focuses on gameplay FEEL (pacing, atmosphere, mechanics, challenge),
not plot. It's designed to produce dense, consistent embeddings that capture
the actual game experience — solving IGDB's poor keyword quality.

Resumable. ~1.5-3.5h depending on model and hardware.

Usage:
  # Start Ollama server first:
  /Applications/Ollama.app/Contents/Resources/ollama serve &

  python3 archive/enrich_descriptions.py [--model qwen3:1.7b] [--workers 2]
"""
import json, urllib.request, time, os, sys, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE    = os.path.dirname(os.path.abspath(__file__))
BACKLOG = os.path.join(BASE, '..', 'backlog.json')
META    = os.path.join(BASE, '..', 'backlog_meta.json')
STEAM   = os.path.join(BASE, '..', 'steam_tags.json')
WIKI    = os.path.join(BASE, '..', 'wiki_summaries.json')
OUT     = os.path.join(BASE, '..', 'enriched_descriptions.json')

OLLAMA_URL = 'http://localhost:11434/api/generate'
SAVE_EVERY = 100

PROMPT_TEMPLATE = """\
You are a video game expert writing a short description for a recommendation engine.
Based on the data below, write a single paragraph (60-80 words) describing this game's GAMEPLAY FEEL.

Focus ONLY on: pacing (fast/slow/methodical), atmosphere (dark/cozy/tense/mysterious), core mechanics, \
type of challenge (reaction/puzzle/strategic/narrative), emotional tone, and what kind of player loves it.
Do NOT mention the title, plot spoilers, or characters by name.
Be specific about mechanics and atmosphere. Use concrete adjectives.

Title: {title}
Genres: {genres}
Themes: {themes}
Perspectives: {perspectives}
IGDB keywords: {keywords}
Steam tags: {steam_tags}
Wikipedia: {wiki}
IGDB summary: {summary}

Write the description now (60-80 words, single paragraph, no title):"""

def build_prompt(game, meta, steam_tags, wiki):
    genres   = ', '.join(game.get('genres')    or [])
    themes   = ', '.join(meta.get('themes')    or [])
    persp    = ', '.join(meta.get('perspectives') or [])
    keywords = ', '.join((meta.get('keywords')  or [])[:20])
    st       = ', '.join(steam_tags[:15]) if steam_tags else 'n/a'
    w        = (wiki or '').strip()[:300] or 'n/a'
    summary  = (meta.get('summary') or '').strip()[:400] or 'n/a'

    return PROMPT_TEMPLATE.format(
        title=game['title'], genres=genres or 'n/a', themes=themes or 'n/a',
        perspectives=persp or 'n/a', keywords=keywords or 'n/a',
        steam_tags=st, wiki=w, summary=summary,
    )

def has_enough_data(game, meta, steam_tags, wiki):
    """Skip games with basically no data or very low quality."""
    # Only enrich games with IGDB rating ≥ 70 or no rating (unknown/new)
    rating = game.get('igdb_rating') or 0
    if rating > 0 and rating < 70:
        return False
    has_summary = bool((meta.get('summary') or '').strip())
    has_steam   = bool(steam_tags)
    has_wiki    = bool((wiki or '').strip())
    has_genres  = bool(game.get('genres'))
    return sum([has_summary, has_steam, has_wiki, has_genres]) >= 2

def ollama_generate(prompt, model):
    body = json.dumps({'model': model, 'prompt': prompt, 'stream': False,
                       'think': False,
                       'options': {'temperature': 0.3, 'num_predict': 150}}).encode()
    req  = urllib.request.Request(OLLAMA_URL, data=body,
                                  headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = json.load(r)
    return data.get('response', '').strip()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model',   default='qwen3:1.7b')
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()

    print(f'Model: {args.model}  Workers: {args.workers}')

    # Check Ollama is up
    try:
        with urllib.request.urlopen('http://localhost:11434/', timeout=5) as r:
            pass
    except Exception:
        print('ERROR: Ollama not running. Start with:')
        print('  /Applications/Ollama.app/Contents/Resources/ollama serve &')
        sys.exit(1)

    # Load data
    print('Loading data...')
    backlog    = json.load(open(BACKLOG))
    meta_all   = json.load(open(META))
    steam_all  = json.load(open(STEAM))   if os.path.exists(STEAM) else {}
    wiki_all   = json.load(open(WIKI))    if os.path.exists(WIKI)  else {}

    result = {}
    if os.path.exists(OUT):
        result = json.load(open(OUT))
        print(f'Resuming: {len(result)} already done')

    need = [g for g in backlog if str(g['igdb_id']) not in result]

    # Filter to games with enough data
    need_data = []
    skipped   = 0
    for g in need:
        igdb_id  = str(g['igdb_id'])
        m        = meta_all.get(igdb_id, {})
        st       = steam_all.get(igdb_id, [])
        w        = wiki_all.get(igdb_id, '')
        if has_enough_data(g, m, st, w):
            need_data.append((g, m, st, w))
        else:
            result[igdb_id] = ''   # no data → empty, skip
            skipped += 1

    total = len(need_data)
    print(f'Remaining: {total}  (skipped {skipped} with insufficient data)')
    if not total:
        print('All done!')
        return

    print(f'\nGenerating descriptions... (~{total * 22 // 600} min estimated at 2.2s/game)')

    done     = 0
    save_ctr = 0

    def worker(item):
        g, m, st, w = item
        prompt = build_prompt(g, m, st, w)
        try:
            text = ollama_generate(prompt, args.model)
            # Strip thinking tags if model outputs them (qwen3 sometimes does)
            if '<think>' in text:
                text = text.split('</think>')[-1].strip()
            return str(g['igdb_id']), text
        except Exception as e:
            return str(g['igdb_id']), ''

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(worker, item): item for item in need_data}
        for fut in as_completed(futs):
            igdb_id, text = fut.result()
            result[igdb_id] = text
            done     += 1
            save_ctr += 1
            if save_ctr >= SAVE_EVERY:
                with open(OUT, 'w') as f:
                    json.dump(result, f, ensure_ascii=False, separators=(',', ':'))
                save_ctr = 0
            if done % 200 == 0 or done == total:
                with_text = sum(1 for v in result.values() if v)
                elapsed   = done  # proxy
                print(f'  {done}/{total} ({done/total*100:.0f}%)  with_text={with_text}', flush=True)

    with open(OUT, 'w') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))

    with_text = sum(1 for v in result.values() if v)
    size_kb   = os.path.getsize(OUT) / 1024
    print(f'\nDone! {len(result)} entries, {with_text} with descriptions ({size_kb:.0f} KB)')

    # Sample output
    print('\nSamples:')
    for title in ['Blue Prince', 'Hollow Knight', 'Elden Ring']:
        g    = next((x for x in backlog if x['title'].lower() == title.lower()), None)
        if g:
            desc = result.get(str(g['igdb_id']), '')
            print(f'\n  {title}:\n  {desc[:200]}')

if __name__ == '__main__':
    main()
