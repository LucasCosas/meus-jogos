#!/usr/bin/env python3
"""
Enriches game descriptions using multiple Groq models in parallel.
Each model has an independent token quota → combined throughput ~10x faster.

Models used (each with separate rate limits):
  - meta-llama/llama-4-scout-17b-16e-instruct  (30k tok/min, 1k req/day)
  - llama-3.3-70b-versatile                     (12k tok/min, 1k req/day)
  - openai/gpt-oss-120b                          (8k tok/min,  1k req/day)
  - openai/gpt-oss-20b                           (8k tok/min,  1k req/day)
  - qwen/qwen3-32b                               (6k tok/min,  1k req/day)
  - llama-3.1-8b-instant                         (6k tok/min, 14k req/day)  ← handles overflow

Output: data/enriched_descriptions.json
Run:    python3 scripts/enrich_groq_multi.py
"""
import json, time, os, sys, threading, warnings
warnings.filterwarnings('ignore')
import requests

BASE    = os.path.dirname(os.path.abspath(__file__))
ROOT    = os.path.join(BASE, '..')
DATA    = os.path.join(BASE, '..', 'data')
BACKLOG = os.path.join(ROOT, 'backlog.json')
META    = os.path.join(DATA, 'backlog_meta.json')
STEAM   = os.path.join(DATA, 'steam_tags.json')
WIKI    = os.path.join(DATA, 'wiki_summaries.json')
OUT     = os.path.join(DATA, 'enriched_descriptions.json')

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'

# Models with their token-per-minute limits and per-minute delay
# delay = 60 / (tok_per_min / 480 tokens_per_game) + buffer

# (name, tok/min, delay_secs, max_games, api_key_var)
# delay = 60 / (tok_per_min / 880 tokens_per_req) + 1s buffer
# KEY1 models
MODELS_KEY1 = [
    ('openai/gpt-oss-120b',        8000,  8.0,  999),
    ('openai/gpt-oss-20b',         8000,  8.0,  999),
    ('qwen/qwen3-32b',             6000, 10.0,  999),
    ('allam-2-7b',                 6000, 10.0, 6999),
]
# KEY2 models (second account — separate daily quotas)
MODELS_KEY2 = [
    ('meta-llama/llama-4-scout-17b-16e-instruct', 30000,  2.0,  999),
    ('llama-3.1-8b-instant',                       6000, 10.0, 6999),
    ('llama-3.3-70b-versatile',                   12000,  5.5,  999),
    ('openai/gpt-oss-120b',                        8000,  8.0,  999),
    ('openai/gpt-oss-20b',                         8000,  8.0,  999),
]
# KEY3 models (third account — separate daily quotas)
MODELS_KEY3 = [
    ('meta-llama/llama-4-scout-17b-16e-instruct', 30000,  2.0,  999),
    ('llama-3.3-70b-versatile',                   12000,  5.5,  999),
    ('openai/gpt-oss-120b',                        8000,  8.0,  999),
    ('openai/gpt-oss-20b',                         8000,  8.0,  999),
    ('llama-3.1-8b-instant',                       6000, 10.0, 6999),
]

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
    has_summary = bool((meta.get('summary') or '').strip())
    has_steam   = bool(steam_tags)
    has_wiki    = bool((wiki or '').strip())
    has_genres  = bool(game.get('genres'))
    return sum([has_summary, has_steam, has_wiki, has_genres]) >= 2

def groq_call(session, model, prompt, delay):
    """Single Groq call with retry on 429."""
    messages = [{'role': 'user', 'content': prompt}]
    # qwen3 thinks by default and burns all tokens before writing — force direct response
    if 'qwen' in model.lower():
        messages = [
            {'role': 'system', 'content': 'Respond directly. Do not use <think> tags or reasoning blocks. Write only the final answer.'},
            {'role': 'user', 'content': prompt},
        ]
    payload = {
        'model': model,
        'messages': messages,
        'temperature': 0.3,
        'max_tokens': 180,
    }
    for attempt in range(6):
        try:
            r = session.post(GROQ_URL, json=payload, timeout=30)
            if r.status_code == 200:
                text = r.json()['choices'][0]['message']['content'].strip()
                # Strip <think>...</think> reasoning blocks (qwen3 and similar)
                if '</think>' in text:
                    text = text.split('</think>')[-1].strip()
                return text
            elif r.status_code == 429:
                retry_after = int(r.headers.get('Retry-After', 10))
                wait = min(retry_after + 1, 15)  # cap at 15s — token bucket refills fast
                print(f'  [{model.split("/")[-1][:20]}] 429 → wait {wait}s', flush=True)
                time.sleep(wait)
            else:
                print(f'  [{model.split("/")[-1][:20]}] HTTP {r.status_code}', flush=True)
                return ''
        except Exception as e:
            time.sleep(3)
    return ''

# Shared state (thread-safe via lock)
_result   = {}
_lock     = threading.Lock()
_done_ctr = 0
_total    = 0
_t_start  = 0

def save_result():
    with open(OUT, 'w') as f:
        json.dump(_result, f, ensure_ascii=False, separators=(',', ':'))

def worker_thread(model_name, delay, games, meta_all, steam_all, wiki_all, api_key):
    global _done_ctr
    session = requests.Session()
    session.headers.update({
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    })
    short = model_name.split('/')[-1][:22]
    local_done = 0
    local_save = 0
    print(f'  [{short}] started ({len(games)} games)', flush=True)

    for game in games:
        iid = str(game['igdb_id'])

        # Skip if another thread already did it
        with _lock:
            if iid in _result:
                continue

        m   = meta_all.get(iid, {})
        st  = steam_all.get(iid, [])
        w   = wiki_all.get(iid, '')

        if not has_enough_data(game, m, st, w):
            with _lock:
                _result[iid] = ''
            continue

        prompt = build_prompt(game, m, st, w)
        text   = groq_call(session, model_name, prompt, delay)
        time.sleep(delay)

        with _lock:
            _result[iid] = text
            _done_ctr   += 1
            local_done  += 1
            local_save  += 1
            done_snap    = _done_ctr
            total_snap   = _total

            if local_save >= 50:
                save_result()
                local_save = 0

        if local_done % 10 == 0:
            elapsed = time.time() - _t_start
            rate    = done_snap / max(elapsed / 60, 0.01)
            eta     = (total_snap - done_snap) / max(rate, 0.1)
            print(f'  [{short}] {local_done} done  '
                  f'total={done_snap}/{total_snap}  '
                  f'rate={rate:.0f}/min  ETA={eta:.0f}min', flush=True)

    print(f'  [{short}] FINISHED ({local_done} games)', flush=True)

def main():
    global _result, _total, _t_start

    key1 = os.environ.get('GROQ_API_KEY', '')
    key2 = os.environ.get('GROQ_API_KEY2', '')
    key3 = os.environ.get('GROQ_API_KEY3', '')
    if not key1:
        print('ERROR: export GROQ_API_KEY=gsk_...')
        sys.exit(1)

    # Build combined worker list: (model_name, tpm, delay, max_games, api_key)
    ALL_MODELS = [(m[0], m[1], m[2], m[3], key1) for m in MODELS_KEY1]
    if key2:
        ALL_MODELS += [(m[0], m[1], m[2], m[3], key2) for m in MODELS_KEY2]
    if key3:
        ALL_MODELS += [(m[0], m[1], m[2], m[3], key3) for m in MODELS_KEY3]
    n_keys = sum([1, bool(key2), bool(key3)])
    print(f'Using {n_keys} API key(s) — {len(ALL_MODELS)} workers total', flush=True)

    print('Loading data...', flush=True)
    backlog   = json.load(open(BACKLOG))
    meta_all  = json.load(open(META))
    steam_all = json.load(open(STEAM))   if os.path.exists(STEAM) else {}
    wiki_all  = json.load(open(WIKI))    if os.path.exists(WIKI)  else {}

    _result = {}
    if os.path.exists(OUT):
        _result = json.load(open(OUT))
        print(f'Resuming: {len(_result)} already done', flush=True)

    need = [g for g in backlog if str(g['igdb_id']) not in _result]
    print(f'Remaining: {len(need)} games', flush=True)

    if not need:
        print('All done!')
        return

    _total   = len(need)
    _t_start = time.time()

    # Distribute games evenly across all active workers (respecting max_games cap)
    import math
    num_workers = len(ALL_MODELS)
    share = math.ceil(len(need) / num_workers)

    model_buckets = {}
    remaining_games = list(need)
    for model_name, _, delay, max_games, api_key in ALL_MODELS:
        key = (model_name, api_key[-8:])   # (name, key-suffix) to distinguish same model on different keys
        alloc = min(share, max_games, len(remaining_games))
        take = remaining_games[:alloc]
        model_buckets[key] = (model_name, delay, take, api_key)
        remaining_games = remaining_games[alloc:]
        if not remaining_games:
            break

    # Any leftovers (due to rounding) go to first worker with capacity
    for key in model_buckets:
        if not remaining_games:
            break
        model_name, delay, bucket, api_key = model_buckets[key]
        _, _, _, max_games, _ = next(m for m in ALL_MODELS if m[0] == model_name and m[4] == api_key)
        space = max_games - len(bucket)
        if space > 0:
            extra = remaining_games[:space]
            model_buckets[key] = (model_name, delay, bucket + extra, api_key)
            remaining_games = remaining_games[space:]

    if remaining_games:
        print(f'WARNING: {len(remaining_games)} games not assigned (increase max_games caps)', flush=True)

    print('\nGame distribution:', flush=True)
    for (model_name, key_sfx), (_, delay, bucket, _api) in model_buckets.items():
        if bucket:
            games_per_min = 60 / delay
            est = len(bucket) / games_per_min
            print(f'  {model_name.split("/")[-1]:<35} key=…{key_sfx}  {len(bucket):>5} games  '
                  f'~{delay}s/game  ETA≈{est:.0f}min', flush=True)

    print('\nStarting all workers...', flush=True)

    threads = []
    for (model_name, key_sfx), (_, delay, bucket, api_key) in model_buckets.items():
        if not bucket:
            continue
        t = threading.Thread(
            target=worker_thread,
            args=(model_name, delay, bucket, meta_all, steam_all, wiki_all, api_key),
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(0.5)   # stagger starts slightly

    for t in threads:
        t.join()

    save_result()

    with_text = sum(1 for v in _result.values() if v)
    size_kb   = os.path.getsize(OUT) / 1024
    elapsed   = (time.time() - _t_start) / 60
    print(f'\nDone in {elapsed:.0f} min! '
          f'{len(_result)} entries, {with_text} with descriptions ({size_kb:.0f} KB)', flush=True)

    print('\nSamples:')
    for title in ['Blue Prince', 'Hollow Knight', 'Elden Ring']:
        g = next((x for x in backlog if x['title'].lower() == title.lower()), None)
        if g:
            desc = _result.get(str(g['igdb_id']), '')
            print(f'\n  {title}:\n  {desc[:200]}')

if __name__ == '__main__':
    main()
