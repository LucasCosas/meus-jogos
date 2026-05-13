# Development Log — Gamelog

> Registro cronológico de features implementadas, decisões técnicas e bugs resolvidos.
> Formato: data → o que foi feito → detalhes técnicos relevantes.

---

## 2026-05-13 — Motor de Recomendação v2 (Stage 1)
**Arquivos:** `index.html`  **Commit:** `ec2944f`

### Modelo de afinidade corrigido
Afinidade agora usa `(rating - 5) / 5 → [-1, +1]`. Antes: avg bruto (1–10) / 10, nunca penalizava. Agora: nota 2 → -0.6, nota 5 → neutro, nota 9 → +0.8.

### Subgêneros como cidadãos de primeira classe
- `SUBGENRE_ALIASES` mapeia nomes do catálogo do usuário para subgêneros do backlog (`soulslike → Soulslike`, `metroidvania → Metroidvania`, etc.)
- `computeUserProfile` agora rastreia `subgenreAffinity` separada de `genreAffinity`
- Picker na UI usa `<optgroup>` separando Gêneros e Subgêneros
- Backlog tem 4 subgêneros: Soulslike (80 jogos), Metroidvania (224), Roguelite (154), Roguelike (241)

### Scorer multi-sinal com pesos ajustáveis
5 sinais, todos normalizados para [0,1]:

| Sinal | Função | Peso padrão |
|-------|---------|-------------|
| `genre_fit` | `genreFit(game, profile)` | 6 |
| `subgenre_fit` | `subgenreFit(game, profile)` | 4 |
| `igdb_score` | `igdbScore01(game)` — Bayesian, modificado por behavior | 5 |
| `community_score` | `communityScore01(game)` | 2 |
| `platform_fit` | `platformFit(game, userPlatforms)` | 3 |

Score final: `Σ(sinal × peso) / Σ(pesos)`

### Modos comportamentais
- **Balanceado** — pesos padrão
- **Hidden Gems** — `igdbScore01` aplica penalidade de popularidade: `base × (1 - min(1, count/500) × 0.45)`
- **Top Rated** — filtra jogos com `igdb_rating_count < 100`

### Modo "Parecido com X" reformulado
Blend de 50% content-based + 50% similaridade Jaccard:
`score = baseScore × 0.5 + (genSim × 0.6 + subSim × 0.4) × 0.5`

### UI
- Painel de pesos colapsável com sliders 0–10 e preview em tempo real
- Filtro de plataforma + toggle "Excluir wishlist"
- Cards mostram breakdown de sinais com chips coloridos (verde = positivo, vermelho = negativo)

---

## 2026-05-13

### Motor de Recomendação v1 + Wishlist
**Arquivos:** `index.html`

Implementado sistema de recomendações em dois modos:

**Modo "Por Gênero"**
- Dropdown populado com gêneros reais do backlog (IGDB), ordenados por afinidade do usuário
- Score: `igdb_bayesian × 0.6 + user_fit × 0.4`
- `user_fit` = média das notas do usuário nos jogos com aquele gênero, normalizada 0–1
- Afinidade computada em `computeUserProfile()` com normalização de nomes via `GENRE_ALIASES` (resolve mismatch entre nomes do catálogo e IGDB)

**Modo "Parecido com X"**
- Autocomplete busca em jogos jogados + backlog
- Score: `jaccard_gênero × 0.3 + jaccard_subgênero × 0.3 + user_fit × 0.2 + igdb × 0.2`
- Jaccard similarity entre arrays de gêneros/subgêneros

**Wishlist**
- Persistida em `localStorage` (`gamelog_wishlist`) como array de `igdb_id`
- Toggle por `igdb_id` com atualização reativa nos cards de recomendação
- `startPlayingWishlist()` — move jogo para o catálogo abrindo modal pré-preenchido com gêneros e igdb_id

**Bug detectado e corrigido (mesmo dia):** gêneros do catálogo do usuário não batiam com gêneros do backlog (IGDB). Ex: usuário tinha "RPG" mas backlog usava "Role-playing (RPG)". Corrigido com `GENRE_ALIASES` em `normalizeGenre()` e dropdown refeito a partir dos gêneros reais do backlog.

---

### Correção de 11 bugs (sessão anterior, mesma data)
**Arquivos:** `index.html`

| # | Bug | Fix |
|---|-----|-----|
| 1 | Modal mostrava campo `hours` em vez de `estimated_hours` | Pre-fill com `estimated_hours \|\| hours`; `saveGame` escreve em `estimated_hours` |
| 2 | `startPlayingWishlist` não preenchia gêneros | Substituído `getElementById('game-genres')` (inexistente) por `buildGenreChips(g.genres)` |
| 3 | "Já joguei" no backlog adicionava jogo sem pedir rating/playtime | Agora abre modal pré-preenchido em vez de inserir silenciosamente |
| 4 | `switchPage` usava `event` global implícito | Função recebe `ev` explícito; onclick passa `event` |
| 5 | Rate mode mostrava "PSN" hardcoded como fallback de plataforma | Fallback virou string vazia |
| 6 | Fechar wizard com "Depois" marcava como concluído permanentemente | `closeHoursWizard` não marca mais; só `saveHoursWizard` faz isso |
| 7 | Apóstrofo em nome de gênero quebrava `onclick` inline em `buildGenreChips` | Migrado para `data-genre` + `addEventListener` |
| 8 | Wishlist descartava silenciosamente jogos não encontrados no backlog | Mostra card placeholder com botão "Remover" |
| 9 | Autocomplete de recomendações não fechava ao clicar fora | `document.addEventListener('click', ...)` fecha ao clicar fora do input/lista |
| 10 | `rawg_id` aparecia nos cards do catálogo sem utilidade | Span removido |
| 11 | Stats contava zerados só por `completed === 'yes'` | Conta também `playtime === 'completed'` |

---

## Entradas anteriores (reconstituídas do histórico)

### Wizard de horas de jogo (uma vez)
**Arquivos:** `index.html`

Modal que aparece uma vez para jogos sem `estimated_hours`. Opções: 1h, 5h, 10h, 25h, 50h, 100h, 300h, Pular. Salva em `estimated_hours` no `games.json`. Flag de conclusão em `localStorage` (`gamelog_hours_wizard_done`). Progresso visual com barra e contador.

---

### `estimated_hours` via IGDB Time To Beat
**Arquivos:** `games.json`, scripts em `archive/`

Busca `game_time_to_beats` na API IGDB para todos os 330 jogos. Mapeia:
- `normally` → tempo base
- `completely` → usado se disponível e razoável (`completely ≤ 6 × normally`)
- Exclui `normally > 500h` (dados corrompidos)
- Heurística de playtime do usuário: `little=25%`, `medium=55%`, `much=90%`, `completed=100%` do tempo base

244 jogos resolvidos via IGDB TTB, 86 via wizard manual. Total: ~9.180h estimadas no catálogo.

---

### Backlog — Performance + Infinite Scroll
**Arquivos:** `index.html`

Problema: abrir a aba de backlog com 15.993 jogos travava o browser (renderizava todos de uma vez).

Solução implementada:
- `IntersectionObserver` com sentinel element para infinite scroll — carrega 80 cards por página
- Debounce de 300ms no campo de busca
- Dropdowns de filtro construídos uma única vez (`_backlogDropdownsBuilt` flag)
- Resultado: carregamento imediato, scroll suave

---

### Backlog — Ordenação Bayesian IGDB
**Arquivos:** `index.html`

Problema: ordenação por nota IGDB colocava jogos com 1 review na primeira posição (ex: Unreal Tournament 100.0 com 1 review).

Solução: Bayesian weighted score com prior `C=3, m=75`:
```
score = (rating × count + 75 × 3) / (count + 3)
```

---

### Dedup e limpeza do catálogo
**Arquivos:** `games.json`, `backlog.json`

- `games.json`: removidos 74 jogos sem playtime (397 → 323)
- Dedup por `igdb_id` entre `games.json` e `backlog.json`
- Corrigidos 5 `igdb_id` errados (AC Brotherhood, AC III, AC Rogue, Marvel's Avengers, Pokémon Ruby — todos apontavam para DLCs ou edições erradas)
- Mescladas 2 entradas duplicadas de The Witcher 3

---

### Limpeza de API keys expostas
**Arquivos:** `.env` (novo), `.gitignore`

RAWG API key estava commitada no histórico do Git (arquivo `fetch_rawg_ids.py`). Ações:
- Nova key gerada no RAWG
- Criado `.env` com todas as chaves (RAWG, IGDB client_id, IGDB client_secret)
- `.env` adicionado ao `.gitignore`
- Scripts movidos para `archive/` com referência à variável de ambiente em vez da key hardcoded

---

### Reorganização do repositório
**Arquivos:** estrutura de pastas

Scripts Python e arquivos de dados auxiliares movidos para `archive/`. Pasta `backups/` removida (estava no `.gitignore` mas os arquivos `.bak` tinham sido commitados; corrigido com `git rm --cached`).

---

## Convenções de desenvolvimento

### Estrutura do `games.json`
```json
{
  "games": [...],
  "profile": { "platforms": [], "subscriptions": [], "customGenres": [] }
}
```

Campos por jogo: `id`, `title`, `rating` (1–10), `year`, `genres[]`, `platformPlayed`, `availableOn[]`, `notes`, `played`, `playtime` (little/medium/much/completed), `completed` (yes/null), `igdb_id`, `igdb_rating`, `estimated_hours`, `rawg_id` (legacy), `_psn` (legacy)

### Estrutura do `backlog.json`
Array de objetos com: `igdb_id`, `title`, `igdb_rating`, `igdb_rating_count`, `community_rating`, `year`, `platforms[]`, `genres[]`, `subgenres[]`

### API keys
Nunca commitar. Ficam em `.env` (gitignored). Ver `.env` local para valores atuais.

### Servidor local
```bash
cd /Users/lucascosas/Documents/claude/jogos
python3 server.py   # porta 7432
```

### Salvar dados
`saveGames()` faz POST para `http://localhost:7432/games.json`. Se o servidor não estiver rodando, cai em localStorage como fallback.
