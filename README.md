# GameLog

Catálogo pessoal de jogos com motor de recomendação semântico. Registra o histórico, acompanha o backlog e recomenda jogos com base no gosto real do usuário — não só por gênero, mas por *vibe* de gameplay.

---

## O que é

GameLog é um app web single-file (`index.html`) que roda localmente. Não precisa de servidor externo nem conta em nenhum serviço. Os dados ficam em arquivos JSON no próprio repositório.

**Funcionalidades principais:**
- **Catálogo** — registro de jogos jogados com nota (1–10), plataforma, tempo de jogo e comentários
- **Backlog** — lista de jogos a jogar, com busca e filtros; carregamento via infinite scroll (6.950 jogos)
- **Wishlist** — fila de espera antes de iniciar um jogo
- **Recomendações** — motor multi-sinal com embeddings semânticos e filtragem por gênero, subgênero, plataforma e rating IGDB
- **Perfil & Stats** — afinidade por gênero, horas estimadas, distribuição por plataforma

---

## Motor de recomendação

O sistema evoluiu em duas gerações:

### Gen 1 — Recomendação por metadados (Jaccard)
Score baseado em similaridade de gênero/subgênero entre o perfil do usuário e os jogos do backlog. Rápido, sem dependências externas, mas limitado à estrutura de categorias do IGDB.

### Gen 2 — Recomendação semântica (embeddings)
Cada jogo recebe uma descrição de 60–80 palavras focada em *gameplay feel* (ritmo, atmosfera, tipo de desafio, tom emocional) — gerada por LLM a partir de dados do IGDB, Steam e Wikipedia. Essa descrição é convertida em um vetor de 1024 dimensões pelo modelo `BAAI/bge-large-en-v1.5`.

**Pipeline completo:**

```
IGDB API ──► backlog_meta.json ─────────────────────────┐
SteamSpy ──► steam_tags.json  ──► enrich_groq_multi.py ──► enriched_descriptions.json
Wikipedia ──► wiki_summaries.json ──────────────────────┘
                                        │
                                        ▼
                              generate_embeddings.py
                              (Colab T4 GPU recomendado)
                                        │
                                        ▼
                                  embeddings.bin
                                        │
                                        ▼
                                   index.html  (busca por similaridade de cosseno)
```

**Sinais usados no scorer final:**

| Sinal | Peso padrão | Descrição |
|-------|-------------|-----------|
| `semantic_similarity` | principal | Cosseno entre vetor da query e vetor do jogo |
| `igdb_score` | modificador | Bayesian weighted (prior C=3, m=75) |
| `genre_fit` | filtro | Afinidade do usuário com os gêneros do jogo |
| `platform_fit` | filtro | Jogo disponível nas plataformas do usuário |
| `year_weight` | decaimento | Penaliza jogos muito antigos suavemente |

**Modos:**
- **Balanceado** — pesos padrão
- **Hidden Gems** — penaliza popularidade (`base × (1 - min(1, count/500) × 0.45)`)
- **Top Rated** — filtra jogos com menos de 100 avaliações no IGDB

---

## Estrutura do repositório

```
jogos/
├── index.html                  ← app completo (HTML/CSS/JS, ~15k linhas)
├── server.py                   ← servidor local na porta 7432
├── backlog.json                ← catálogo de 7.083 jogos (IGDB, sem filtro de ano)
├── games.json                  ← dados do usuário (histórico, notas, perfil)
├── embeddings.bin              ← vetores float32, 1024 dims por jogo (~29MB)
├── .env.example                ← template de variáveis de ambiente
│
├── data/                       ← arquivos de pipeline (não commitados, pesados)
│   ├── backlog_meta.json       ← metadata IGDB: summary, themes, keywords (~15MB)
│   ├── steam_tags.json         ← tags Steam por jogo (~1.6MB)
│   ├── steam_applist.json      ← cache do catálogo Steam (~2MB)
│   ├── wiki_summaries.json     ← intros Wikipedia por jogo
│   ├── enriched_descriptions.json  ← descrições LLM por jogo (~3MB)
│   └── backlog_full.json       ← catálogo original completo (13.587 jogos)
│
├── scripts/                    ← pipeline de dados
│   ├── fetch_meta.py           ← busca metadata do IGDB
│   ├── fetch_steam_tags.py     ← busca tags do SteamSpy
│   ├── fetch_wiki_single.py    ← busca resumos da Wikipedia
│   ├── enrich_groq_multi.py    ← gera descrições LLM (Groq, multi-modelo)
│   ├── generate_embeddings.py  ← gera embeddings (sentence-transformers)
│   ├── cluster_games.py        ← clusteriza com K-means
│   └── query_search.py         ← busca semântica interativa no terminal
│
├── docs/
│   ├── DESIGN_BRIEF.md         ← direção visual e UX do app
│   ├── DEVLOG.md               ← registro cronológico de decisões técnicas
│   ├── ROADMAP.md              ← features planejadas
│   └── ML.md                   ← documentação técnica do motor de ML
│
└── backups/                    ← backups automáticos do server.py (gitignored)
```

---

## Como rodar

### Pré-requisitos
```bash
pip install requests sentence-transformers numpy scikit-learn
```

### App web
```bash
python3 server.py   # http://localhost:7432
```

O servidor serve os arquivos estáticos e aceita POST em `/games.json` para salvar dados (com backup automático).

### Busca semântica no terminal
```bash
python3 scripts/query_search.py

query>   relaxing cozy puzzle exploration
similar> Hollow Knight --top 15
query>   challenging dark fantasy RPG great lore --igdb 80
```

---

## Como o catálogo foi construído

**Fonte:** IGDB API (via Twitch Developer)

**Filtros aplicados:**
- IGDB rating ≥ 60 **ou** sem avaliações (jogos novos/nichados incluídos)
- Plataformas suportadas: PS4, PS5, Xbox One, Xbox Series X|S, Nintendo Switch, PC, Mac, iOS, Android
- Jogos do catálogo pessoal do usuário são adicionados independente de ano ou rating
- Resultado: **7.083 jogos** (sem corte de ano — inclui clássicos pré-2015 jogados pelo usuário)

---

## Pipeline de enriquecimento

### 1. Metadata IGDB
```bash
export IGDB_CLIENT_ID=...
export IGDB_CLIENT_SECRET=...
python3 scripts/fetch_meta.py
```
Busca para cada jogo: summary, storyline, themes, keywords, player_perspectives.

### 2. Tags Steam
```bash
python3 scripts/fetch_steam_tags.py
```
Match por título entre backlog e catálogo do SteamSpy, depois busca tags via API do SteamSpy.

### 3. Resumos Wikipedia
```bash
python3 scripts/fetch_wiki_single.py
```
Estratégia em 3 tentativas por jogo: `"{título} (video game)"` → `"{título}"` → busca textual. Single-threaded com 0.5s de delay para evitar rate limit.

### 4. Descrições LLM (Groq)
```bash
export GROQ_API_KEY=gsk_...
export GROQ_API_KEY2=gsk_...   # opcional: segunda conta para dobrar throughput
python3 scripts/enrich_groq_multi.py
```

Usa múltiplos modelos simultaneamente (cada um tem cota de tokens independente):

| Conta | Modelos |
|-------|---------|
| KEY1 | gpt-oss-120b, gpt-oss-20b, qwen3-32b, allam-2-7b |
| KEY2 | llama-4-scout-17b, llama-3.1-8b, llama-3.3-70b, gpt-oss-120b, gpt-oss-20b |

O prompt pede uma descrição de **60–80 palavras** focada em gameplay feel — ritmo, atmosfera, tipo de desafio, tom emocional — sem spoilers ou nomes de personagens. Exemplo de output para Hollow Knight:

> *Methodical and atmospheric, this underground insect kingdom demands patience and precision. Combat rewards learning enemy patterns through repeated failure, while exploration unfolds nonlinearly across a beautifully hand-drawn world. The pacing is deliberate—slow traversal punctuated by tense boss encounters. Dark, melancholic tone with occasional surreal humor. Appeals to players who love mastery through persistence, environmental storytelling, and the quiet satisfaction of mapping an intricate world.*

O script é resumível: detecta o que já foi gerado e continua de onde parou.

### 5. Embeddings
```bash
# Recomendado: Google Colab (T4 GPU gratuita, ~2 min)
# Local: python3 scripts/generate_embeddings.py  (lento no CPU — use MPS/CUDA)
```
Modelo: `BAAI/bge-large-en-v1.5` (1.3GB, 1024 dims, MTEB ~63.5). Prioridade das fontes por jogo:
1. Descrição LLM (`enriched_descriptions.json`) — melhor sinal (~99% dos jogos)
2. Tags Steam + metadata IGDB — fallback estruturado

Output: `embeddings.bin` — formato binário compacto (`uint32` igdb_id + `float32 × 1024` por jogo, ~29MB para 7k jogos).

Para adicionar jogos incrementalmente sem re-encodar tudo, veja o notebook do Colab — ele faz merge dos vetores novos no bin existente.

---

## Dados do usuário (`games.json`)

```json
{
  "games": [
    {
      "id": "uuid",
      "title": "Elden Ring",
      "igdb_id": 119133,
      "igdb_rating": 96.3,
      "rating": 9,
      "year": 2022,
      "genres": ["Role-playing (RPG)", "Adventure"],
      "platformPlayed": "PlayStation 5",
      "availableOn": ["PlayStation 5", "PC (Microsoft Windows)"],
      "playtime": "completed",
      "completed": "yes",
      "estimated_hours": 80,
      "notes": "Obra-prima. Inacreditável."
    }
  ],
  "profile": {
    "platforms": ["PlayStation 5", "Nintendo Switch"],
    "subscriptions": ["PS Plus Extra"],
    "customGenres": []
  }
}
```

`playtime`: `"little"` / `"medium"` / `"much"` / `"completed"`

---

## Variáveis de ambiente

```bash
# .env (não commitado — ver .env.example)
IGDB_CLIENT_ID=...
IGDB_CLIENT_SECRET=...
GROQ_API_KEY=gsk_...
GROQ_API_KEY2=gsk_...   # opcional
RAWG_API_KEY=...        # legado, não mais usado
```

---

## Decisões técnicas

**Por que single-file (`index.html`)?**
Uso pessoal e frequente — zero overhead de build, deploy ou dependências de frontend. Abre direto no browser.

**Por que Groq em vez de OpenAI/Anthropic?**
Tier gratuito com múltiplos modelos e cotas independentes. Combinando 9 modelos em paralelo (2 contas), o throughput chega a ~60 jogos/min — 6.950 jogos gerados em ~4h sem custo.

**Por que `BAAI/bge-large-en-v1.5`?**
1024 dimensões, MTEB score ~63.5 vs ~56.3 do `all-MiniLM-L6-v2` anterior — diferença substancial em qualidade semântica. O modelo não é viável de rodar no CPU (1.3GB de pesos, encoding lento), por isso o pipeline usa Google Colab com GPU T4 gratuita (~2 min para 7k jogos). Ver `docs/ML.md` para detalhes técnicos.

**Por que sem filtro de ano no backlog?**
O filtro original (2015+) excluía jogos clássicos que o usuário jogou e usa como referência na busca ("similar a Portal 2", "similar a Skyrim"). Jogos do catálogo pessoal são adicionados independente de ano. Jogos novos do IGDB seguem o filtro de rating ≥ 60.
