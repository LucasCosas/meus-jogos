# ML / Recomendação — Documentação Técnica

> Estado atual: maio 2026  
> Escopo: pipeline de embeddings, busca semântica, perfil de usuário, filtros por subgênero.

---

## 1. Visão geral do pipeline

```
backlog.json          ← catálogo de ~7k jogos (IGDB ids, gêneros, subgêneros)
      │
      ▼
[fetch_meta.py]       ← IGDB API: summary, themes, keywords, perspectives
      │                  → data/backlog_meta.json
      ▼
[fetch_steam_tags.py] ← Steam Store API: community tags
      │                  → data/steam_tags.json
      ▼
[enrich_groq_multi.py]← LLM (Groq): gera descrição de 60-80 palavras de "gameplay feel"
      │                  → data/enriched_descriptions.json
      ▼
[generate_embeddings.py] ← BAAI/bge-large-en-v1.5: encode cada jogo como vetor 1024-dim
      │                    → embeddings.bin
      ▼
[index.html]          ← carrega embeddings.bin no browser, computa cosine similarity em JS
```

---

## 2. Por que embeddings de texto?

Embeddings transformam texto em vetores densos num espaço de alta dimensão onde **distância semântica ≈ distância geométrica**. Se dois textos descrevem o mesmo _feel_ de gameplay (ex: "methodical combat, punishing, dark atmosphere"), seus vetores ficam próximos — independente das palavras exatas usadas.

Isso resolve o problema central de recomendação por _conteúdo_: não precisamos de usuários em comum (cold start problem do collaborative filtering), apenas de uma boa representação textual de cada jogo.

### 2.1 Modelo escolhido: BAAI/bge-large-en-v1.5

| Modelo | Dims | Tamanho | MTEB avg | Uso |
|--------|------|---------|----------|-----|
| `all-MiniLM-L6-v2` | 384 | 80 MB | ~56.3 | descartado |
| `BAAI/bge-large-en-v1.5` | 1024 | 1.3 GB | **63.5** | atual |

> **Nota de infra:** bge-large é lento no CPU (macOS mmap torna o loading de 1.3GB muito lento mesmo com MPS). Solução: rodar no Google Colab (T4 GPU gratuita, ~2 min para 7k jogos). O script suporta encoding incremental — só encoda jogos novos e faz merge no `.bin` existente.

**MTEB** (Massive Text Embedding Benchmark) é o benchmark padrão para modelos de embedding. A diferença de ~7 pontos é substancial — significa que bge-large captura nuances semânticas que MiniLM perde.

bge-large é um modelo BERT-like (encoder-only) treinado com **contrastive learning**: pares de texto semanticamente similares são puxados juntos no espaço vetorial, pares dissimilares são afastados. Para jogos, isso é crucial: "fast-paced roguelike with permadeath" e "procedural dungeon crawler with high difficulty" devem ficar próximos mesmo sem compartilhar palavras.

**Normalização L2**: todos os vetores são normalizados para norma unitária. Isso transforma o produto interno (dot product) em **cosine similarity** — a métrica mais usada para busca semântica. `cos(a,b) = a·b` quando `||a|| = ||b|| = 1`.

### 2.2 Texto de entrada

Para cada jogo, o texto embedado é construído em ordem de prioridade:

**Path A (preferido — 98% dos jogos):**
```
{LLM description}. Steam tags: {tag1}, {tag2}, ... Genres: {genre1}, {genre2}
```

**Path B (fallback — jogos sem dados suficientes):**
```
Genres: ... Steam tags: ... Themes: ... IGDB tags: ... Wikipedia: ... IGDB summary: ...
```

O título é **intencionalmente excluído** do texto. Incluir o nome do jogo cria viés: dois jogos com nomes parecidos ficariam próximos por nome, não por gameplay.

---

## 3. Descrições LLM (enrich_groq_multi.py)

### Por que LLM?

IGDB summary e Wikipedia descrevem _o que acontece no jogo_ (narrativa, mundo, personagens). Queremos descrever _como o jogo se sente_ ao jogar: ritmo, atmosfera, tipo de desafio. Isso requer síntese — e LLMs fazem isso bem.

### Prompt

```
Focus ONLY on: pacing (fast/slow/methodical), atmosphere (dark/cozy/tense/mysterious),
core mechanics, type of challenge (reaction/puzzle/strategic/narrative), emotional tone,
and what kind of player loves it.
Do NOT mention the title, plot spoilers, or characters by name.
Be specific about mechanics and atmosphere. Use concrete adjectives.
(60-80 words, single paragraph)
```

Exemplo de output (Elden Ring):
> "This game offers a methodical gameplay feel, where deliberate, calculated movements are rewarded over frantic action. The dark, Gothic atmosphere is underscored by an eerie soundscape and haunting visuals. Players face a steep learning curve that demands patience and persistence, making each victory deeply satisfying. Ideal for those who relish exploration, discovery, and mastering complex systems in a punishing yet fair environment."

### Infraestrutura multi-modelo

O script usa múltiplos modelos Groq em paralelo (threads), cada um com cota independente de tokens/dia. Com 3 API keys e ~9 workers, o throughput foi de ~50-60 jogos/min.

```python
MODELS_KEY1 = [
    ('openai/gpt-oss-120b', 8000 tpm, 8s/req, 999 max),
    ('openai/gpt-oss-20b',  8000 tpm, 8s/req, 999 max),
    ('qwen/qwen3-32b',      6000 tpm, 10s/req, 999 max),
    ('allam-2-7b',          6000 tpm, 10s/req, 6999 max),
]
# + MODELS_KEY2, MODELS_KEY3 (contas separadas = cotas independentes)
```

Distribuição: `share = ceil(total_games / n_workers)` — cada worker recebe uma fatia igual para processamento paralelo sem duplicação.

---

## 4. Formato binário: embeddings.bin

```
[n_games: uint32 little-endian]
for each game:
  [igdb_id: uint32 little-endian]
  [v_0, v_1, ..., v_1023: float32 × 1024, little-endian]
```

Para 6945 jogos com bge-large (1024 dims):
- Tamanho: `4 + 6945 × (4 + 1024×4)` = ~27 MB
- Carregado no browser via `fetch()` + `ArrayBuffer`
- Interpretado com `DataView` e `Float32Array` — zero parsing overhead

O browser mantém todos os 6945 vetores em memória (~27 MB), o que permite cosine similarity em tempo real sem round-trip ao servidor.

---

## 5. Busca semântica no browser (index.html)

### 5.1 Estrutura de dados em JS

```javascript
// Flat Float32Array: [id0, v0_0, v0_1...v0_1023, id1, v1_0...]
ML.embeddings  // Float32Array
ML.DIMS        // 1024
ML.STRIDE      // 1025 = 1 (id) + 1024 (vetor)

ML.igdbIdAt(i)  // ID do i-ésimo jogo
ML.vectorAt(i)  // Float32Array subarray — view zero-copy, sem alloc
ML.dot(a, b)    // produto interno = cosine sim (vetores normalizados)
```

`Float32Array.subarray()` retorna uma _view_ do mesmo buffer — não aloca nova memória. Isso é crítico: com 6945 iterações e 1024 operações cada, qualquer alloc por iteração seria catastrophic para GC.

### 5.2 Perfil do usuário (buildProfileVector)

O perfil é uma média ponderada dos vetores dos jogos avaliados:

```javascript
for (const game of ratedGames) {
  const w  = (game.rating - 5) / 5;   // [-1, +1], nota 5 = neutro
  const gv = ML.vectorAt(idx);
  vec += gv * w;                        // acumula ponderado
}
vec /= ||vec||;                         // normaliza para unit norm
```

- Jogos com nota 10 puxam o perfil fortemente na direção do vetor do jogo
- Jogos com nota 1 empurram **para longe** (peso negativo)
- Jogos com nota 5 são ignorados (`|w| < 0.05`)

Esse é essencialmente um **rocchio algorithm** — clássico de recuperação de informação adaptado para vetores densos.

### 5.3 Score híbrido para recomendação

Para o modo "perfil do usuário":

```
hybrid = 0.65 × cosine_sim + 0.35 × igdb_quality
```

`igdb_quality` é um Bayesian-smoothed IGDB rating:
```
quality = (rating × count + 75 × 100) / (count + 100)
```

Isso suaviza jogos com poucas reviews: um jogo com 3 reviews de 100% fica próximo de 75%, não de 100%.

Para o modo "similar a X":
```
hybrid = 0.92 × cosine_sim + 0.08 × igdb_quality
```
Aqui a similaridade domina — queremos jogos realmente parecidos, não os mais populares.

---

## 6. Subgêneros

Subgêneros são tags mais específicas que gêneros, usadas como filtro na busca.

| Subgênero | Origem | Jogos |
|-----------|--------|-------|
| Roguelike | Manual (IGDB keywords) | ~174 |
| Roguelite | Manual (IGDB keywords) | ~139 |
| Metroidvania | Manual (IGDB keywords) | ~169 |
| Soulslike | Manual (IGDB keywords) | ~70 |
| Puzzle | IGDB genre "Puzzle" | ~1359 |
| Hack & Slash | IGDB genre "Hack and slash/Beat 'em up" | ~475 |
| Fighting | IGDB genre "Fighting" | ~366 |
| Point & Click | IGDB genre "Point-and-click" | ~279 |
| Visual Novel | IGDB genre "Visual Novel" | ~199 |
| Rhythm | IGDB genre "Music" | ~180 |

Quando o usuário ativa um subgênero como filtro, o motor busca apenas os jogos com aquela tag (interseção com o pool de candidatos por cosine sim).

---

## 7. O que foi descartado e por quê

### 7.1 K-means clustering (Grupos de Gosto)

A feature "Grupos de Gosto" agrupava os 6945 jogos em 20 clusters via MiniBatch K-means sobre os embeddings 384-dim. O problema: com embeddings que capturam principalmente _conteúdo_ (gênero, mecânicas), os clusters resultantes são essencialmente rótulos de gênero ("Visual Novel / Story Rich", "Shooter / Arcade") — exatamente o que os gêneros já fazem, com pior explicabilidade.

Embedding de maior qualidade (bge-large) melhoraria a separação, mas o clustering ainda seria um proxy pobre para "gosto". Gosto é bidimensional: preferência de gênero **e** preferência de atributos (dificuldade, atmosfera, ritmo) que cruzam gêneros.

A remoção simplifica o pipeline (sem `clusters.json`, sem passo extra de carregamento) e evita falsa precisão na UI.

### 7.2 Por que não Collaborative Filtering (CF)?

CF (ex: matrix factorization, ALS, LightFM) usa o padrão de quem avaliou o quê para recomendar. Para funcionar bem precisa de:
- Muitos usuários (ao menos centenas)
- Muitas interações por usuário

Com um único usuário, CF puro degenera. **LightFM** é uma opção híbrida que combina CF com features de item (nossos embeddings), mas ainda precisaria de múltiplos usuários para as latent factors fazerem sentido. É o próximo passo natural se o app for multiusuário.

---

## 8. Pesquisas de referência

### beeFormer (2024)

**Paper**: "beeFormer: Bridging the Gap Between Semantic and Interaction Similarity in Recommender Systems"

Problema: embeddings de texto capturam similaridade _semântica_ (jogo A e B têm descrições similares), mas não _interacional_ (usuários que jogaram A também jogaram B). As duas não são a mesma coisa — e a interacional é mais preditiva para recomendação.

Solução: fine-tune o SentenceTransformer usando dados de interação como sinal de supervisão. O modelo aprende a aproximar vetores de itens que co-ocorrem nas sessões de usuários.

Para este projeto: seria viável se houvesse dados de interação reais (ex: logs de qual jogo foi aberto após outro). Com apenas ratings, precisaríamos de mais usuários.

### LightFM (Kula 2015)

Modelo híbrido: fatoração de matriz (BPR ou WARP loss) + feature embeddings de itens/usuários. A loss WARP (Weighted Approximate-Rank Pairwise) otimiza diretamente para ranking — ideal para recomendação onde queremos o item relevante no top-K, não minimizar MSE de rating.

```
score(u, i) = user_bias[u] + item_bias[i] + user_emb[u]·item_emb[i]
            + user_emb[u]·item_features_emb[i]  # híbrido
```

O componente `item_features_emb` pode ser inicializado com os nossos bge-large embeddings — isso é transfer learning de content para CF.

### Por que cosine similarity > Euclidean para embeddings

Vetores de embedding tendem a ter magnitudes variáveis (mesmo após normalização L2 de treino, os vetores de textos muito curtos vs longos ficam em diferentes "zonas"). Cosine similarity foca no **ângulo** entre vetores, ignorando magnitude — o que captura melhor similaridade semântica. Após normalização para unit norm, `cosine_sim(a,b) = a·b`, tornando o cálculo tão barato quanto dot product.

---

## 9. Próximos passos possíveis

1. **Wikipedia enrichment**: ainda faltam ~20% dos jogos sem description LLM, e muitos poderiam ter Wikipedia summary como backup. O fetch foi bloqueado por rate limit do Wikipedia.

2. **bge-large fine-tuning**: com dados de ratings do usuário (pares positivos/negativos), seria possível fazer fine-tuning do bge-large para aproximar jogos que o usuário tende a gostar conjuntamente — isso é o conceito central do beeFormer aplicado a dados de rating.

3. **Query expansion**: quando o usuário pesquisa "similar a Hollow Knight", poderíamos também usar o texto da query para busca (além do vetor do jogo). bge-large suporta asymmetric search com prefixo `"Represent this sentence:"` para queries.

4. **LightFM multiusuário**: se o app crescer para múltiplos usuários, LightFM com WARP loss inicializado com bge-large embeddings seria o upgrade natural de content-based para híbrido.
