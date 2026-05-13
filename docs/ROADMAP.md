# Product Roadmap — Gamelog

> Documento de planejamento de produto. Atualizado conforme features são planejadas ou priorizadas.
> Última atualização: 2026-05-13 (algoritmo v2 + roadmap GPU adicionados)

---

## Visão do Produto

Um catálogo pessoal de jogos com motor de recomendação inteligente, que aprende com seus gostos e conecta você a outros jogadores. Começa como ferramenta solo, evolui para uma plataforma social mínima entre amigos.

---

## Status atual

- App single-page (HTML/CSS/JS), servido via Python HTTP na porta 7432
- Dados em `games.json` (330 jogos jogados) e `backlog.json` (15.993 jogos do IGDB)
- Features ativas: Catálogo, Backlog, Wishlist, Recomendações (v1), Perfil & Stats

---

## Iniciativas em andamento

### 🔴 REC-001 — Motor de Recomendação v2
**Status:** Em execução  
**Prioridade:** P0

#### Contexto
O motor v1 tem dois problemas críticos:
1. Afinidade de gênero não penaliza ativamente jogos com notas baixas — apenas deixa de favorecê-los
2. Subgêneros (Soulslike, Metroidvania, Roguelite) são ignorados no modo "por gênero"

#### Arquitetura: pipeline em 2 estágios

**Stage 1 — Content-based (local, instantâneo)**
Gera até 50 candidatos do backlog usando scoring multi-sinal com pesos ajustáveis pelo usuário.

Sinais e pesos padrão:

| Sinal | Descrição | Peso padrão |
|-------|-----------|-------------|
| `genre_fit` | Afinidade nos gêneros — positiva e negativa | 0.30 |
| `subgenre_fit` | Afinidade nos subgêneros (Soulslike, Metroidvania...) | 0.20 |
| `igdb_score` | Bayesian IGDB (penaliza poucos reviews) | 0.25 |
| `community_score` | Nota da comunidade IGDB | 0.10 |
| `platform_fit` | Disponível nas plataformas do usuário | 0.15 |

**Modelo de afinidade (corrigido):**
```
affinity = (rating - 5) / 5   →   range [-1.0, +1.0]
nota 2  → -0.6  (penaliza ativamente)
nota 5  →  0.0  (neutro)
nota 9  → +0.8  (favorece ativamente)
```

Modos comportamentais (radio buttons na UI):
- **Balanceado** — pesos padrão
- **Hidden Gems** — boost para jogos com `igdb_rating_count < 200` e nota alta
- **Top Rated** — filtra jogos com `count < 100`, reforça igdb_score

Filtros adicionais:
- Plataforma (dropdown)
- Ano mínimo (slider)
- Excluir jogos já na wishlist (toggle, padrão: sim)

**Stage 2 — LLM Reranker (Claude API, opcional)**
Recebe o perfil do usuário + os 50 candidatos do Stage 1. Retorna lista re-ranqueada com explicações em linguagem natural. O LLM captura contexto que score numérico não captura (ex: DNA compartilhado entre jogos além de tags).

Payload enviado:
- Top 5 gêneros/subgêneros com maior afinidade
- Top 5 jogos mais bem avaliados pelo usuário
- Gêneros/subgêneros com afinidade negativa (notas baixas)
- Os 50 candidatos: título, gêneros, subgêneros, nota IGDB, plataformas

#### Critérios de aceitação
- [ ] Afinidade negativa penaliza ativamente o score final
- [ ] Subgêneros aparecem no picker e entram no cálculo de `subgenre_fit`
- [ ] Painel de pesos visível e funcional (sliders, normaliza para somar 100%)
- [ ] Modos Balanceado / Hidden Gems / Top Rated funcionando
- [ ] Filtro de plataforma e ano na aba de Recomendações
- [ ] Stage 2 (LLM): botão "Aprofundar com IA" que chama Claude API e retorna explicações
- [ ] Explicação por card mostra breakdown dos sinais individuais

---

## Backlog de features

### 🟡 AUTH-001 — Multi-usuário: registro e login
**Prioridade:** P1  
**Dependências:** Deploy (INFRA-001)

#### Contexto
Hoje o app é single-user. Múltiplas pessoas (ex: Lucas + Isabela) não conseguem usar sem conflito de dados.

#### O que queremos
- Cada usuário tem seu próprio catálogo, backlog, wishlist e perfil de recomendação
- Login simples (email + senha ou OAuth com Google/GitHub)
- Dados separados por usuário no backend

#### Decisões técnicas pendentes
- **Armazenamento:** hoje tudo em JSON local. Com multi-usuário precisamos de um backend real. Opções: Supabase (BaaS com auth embutido, PostgreSQL, gratuito até certo uso), Firebase, ou servidor próprio com SQLite
- **Recomendado:** Supabase — tem auth pronto, row-level security, API REST gerada automaticamente, free tier generoso
- **Migração:** `games.json` do Lucas vira seed da tabela `games` para o user_id dele

#### User stories
- Como usuário novo, quero criar uma conta com email/senha para ter meu catálogo próprio
- Como usuário existente (Lucas), quero que meu histórico seja migrado automaticamente
- Como usuário, quero fazer login e ver só os meus dados

#### Critérios de aceitação
- [ ] Tela de login/cadastro (pode ser modal simples)
- [ ] Token de sessão persistido (localStorage ou cookie httpOnly)
- [ ] Todos os dados isolados por user_id
- [ ] Migração de games.json para o primeiro usuário

---

### 🟡 SOCIAL-001 — Recomendar jogos para outros usuários
**Prioridade:** P1  
**Dependências:** AUTH-001

#### Contexto
"Vi que a Isabela ainda não jogou X — quero recomendar pra ela."

#### O que queremos
- Ver o catálogo de outros usuários da plataforma (com permissão)
- Enviar uma recomendação de jogo com mensagem opcional
- Destinatário recebe notificação/badge na interface
- Histórico de recomendações enviadas e recebidas

#### Decisões técnicas pendentes
- Sistema de "amigos" (seguir/aceitar) vs. link direto (qualquer um com a URL pode ver)
- Notificações: in-app (simples) ou email (Resend/SendGrid)
- Privacidade: catálogo público, privado ou só para amigos

#### User stories
- Como usuário, quero buscar outro usuário pelo nome/email e ver seus jogos
- Como usuário, quero recomendar um jogo para um amigo com uma mensagem
- Como usuário, quero ver as recomendações que recebi e adicioná-las à wishlist com um clique

#### Critérios de aceitação
- [ ] Busca de usuários
- [ ] Perfil público de outro usuário (catálogo + stats)
- [ ] Botão "Recomendar para..." em qualquer card do backlog/recomendações
- [ ] Inbox de recomendações recebidas (nova aba ou badge no perfil)
- [ ] "Adicionar à wishlist" a partir de uma recomendação recebida

---

### 🟡 DESIGN-001 — Redesign visual
**Prioridade:** P1  
**Dependências:** Nenhuma (pode ser feito paralelo)

#### Contexto
Novo visual sendo preparado no Claude Design. Quando o design estiver pronto, implementar no app.

#### O que queremos
- Aplicar o novo sistema de design (cores, tipografia, componentes)
- Manter toda a funcionalidade existente
- Garantir responsividade (mobile-first ou pelo menos funcional em mobile)

#### Critérios de aceitação
- [ ] Design system definido (tokens de cor, tipografia, espaçamento)
- [ ] Todos os componentes existentes reimplementados no novo visual
- [ ] Testado em mobile (375px) e desktop (1280px+)

---

### 🟡 INFRA-001 — Deploy em produção
**Prioridade:** P1  
**Dependências:** AUTH-001 (idealmente, mas pode lançar single-user primeiro)

#### Contexto
Hoje o app só roda localmente. Queremos um domínio público.

#### Plano de deploy (guia passo a passo)

**Opção recomendada: Vercel + Supabase**
- Vercel hospeda o front-end (gratuito para projetos pessoais)
- Supabase cuida do banco de dados e autenticação
- Domínio customizado via Vercel (você compra o domínio, configura DNS)

**Passos:**
1. Comprar domínio (Namecheap, Porkbun ou Registro.br para `.com.br`)
2. Criar conta Vercel, conectar ao repositório GitHub
3. Criar projeto Supabase, migrar dados
4. Configurar variáveis de ambiente (API keys) no Vercel
5. Apontar domínio para Vercel (registros DNS A/CNAME)
6. Configurar HTTPS (automático no Vercel)

> Quando chegar nesse passo, o processo será guiado em detalhes.

---

### 🟢 DISC-001 — Features de descoberta
**Prioridade:** P2  
**Dependências:** REC-001

| Feature | Lógica | Status |
|---------|--------|--------|
| **Próximo a jogar** | Intersecção wishlist + recomendações + plataformas disponíveis, ordenada por score | Planejado |
| **Hora de rejogar** | Jogos com nota ≥ 8, playtime = completed, jogados há 3+ anos | Planejado |
| **PS Plus / Game Pass** | Filtrar recomendações por assinaturas ativas do usuário | Planejado — precisa de fonte de dados atualizada |

---

## Próximos passos: Motor de Recomendação v2.1 (sem GPU)

Melhorias incrementais no Stage 1 atual, viáveis no browser:

### A. Regressão linear nos pesos (maior impacto)
Em vez de sliders ajustados manualmente, aprender os pesos que melhor explicam as próprias notas do usuário.

Para cada jogo avaliado no catálogo, calcular os sinais como features e a nota como label. Gradiente descendente minimiza o erro de previsão.

```
nota_prevista = w1×genre_fit + w2×subgenre_fit + w3×igdb + w4×community + b
minimizar:      Σ(nota_real - nota_prevista)²
```

330 amostras, 5 features — viável 100% no browser. Os sliders se tornam display dos pesos aprendidos, não input manual.

### B. kNN baseado em similaridade de jogos
Para cada jogo do backlog, achar os k jogos mais similares do catálogo e prever a nota como média ponderada pela similaridade. Captura padrões não-lineares: adorar Dark Souls (10) mas detestar The Surge (4) mesmo sendo ambos Soulslike.

```
score(jogo) = Σ( sim(jogo, jogo_seu) × sua_nota ) / Σ(sim)
```

### C. Decay temporal
Jogos avaliados recentemente pesam mais no perfil. Gosto muda com o tempo.

```
peso = nota × e^(−λ × anos_desde_que_jogou)
```
Requer campo `year` preenchido (hoje ~70% dos jogos têm).

### D. Histórico de recomendações mostradas
Penalizar progressivamente jogos já exibidos para evitar repetição entre sessões. Persistir em localStorage.

---

## Motor de Recomendação v3 — Com GPU disponível

> Se houver acesso a uma GPU (cloud ou local), a arquitetura muda completamente.

### Por que GPU muda o jogo

Sem GPU: Jaccard em vetores de gênero (máximo ~20 dimensões). Com GPU: embeddings densos de centenas de dimensões sobre texto rico — descrição, tags, mecânicas — capturando semântica que tags não capturam.

Exemplo: "dark atmospheric narrative-driven games" como preferência, mesmo sem tag específica.

---

### Opção 1: Embeddings semânticos de jogos (recomendado)

**Pipeline:**
1. Buscar `summary` + `storyline` de cada jogo via IGDB API (~16k jogos)
2. Codificar com modelo de embedding leve (ex: `all-MiniLM-L6-v2`, 80MB) rodando localmente via ONNX no browser ou num servidor Python simples
3. Perfil do usuário = média ponderada pelos ratings dos embeddings dos jogos jogados
4. Score de recomendação = cosine similarity entre perfil e cada jogo do backlog

**O que isso captura que Jaccard não captura:**
- "Jogos com atmosfera pesada e narrativa não-linear" → sem tag, mas similar semanticamente
- Diferença entre RPG de ação rápida (Nier) e RPG tático lento (XCOM)
- Humor, tom, ritmo de gameplay

**Custo:** modelo de 80MB, inferência em ~100ms por batch de 1k jogos numa GPU simples. Embeddings pré-computados para os 16k jogos do backlog (roda uma vez, salva).

---

### Opção 2: LLM reranker local (substitui Stage 2 Claude API)

Rodar **Llama 3.1 8B** ou **Mistral 7B** localmente para o reranker do Stage 2. Zero custo por chamada, latência aceitável (~2–5s numa GPU de consumidor).

Vantagem sobre Claude API: sem custo recorrente, privacidade total, pode chamar em toda sessão de recomendação sem preocupação com saldo.

---

### Opção 3: Two-Tower Model (com múltiplos usuários)

Requer dados de múltiplos usuários (pós AUTH-001). Aprende embeddings separados de usuário e de jogo em espaço compartilhado — o produto interno prevê o rating.

```
score(usuário, jogo) = embedding_usuário · embedding_jogo
treinar com: ratings de todos os usuários
```

Isso é o que Netflix, Spotify e Steam fazem. Com GPU e ~100+ usuários ativos, torna-se viável. É o teto de qualidade desta arquitetura.

---

### Hardware mínimo para cada opção

| Opção | GPU mínima | VRAM | Custo cloud (spot) |
|-------|-----------|------|-------------------|
| Embeddings (all-MiniLM) | Qualquer CUDA | 2GB | ~$0.10/hora |
| LLM reranker (Mistral 7B) | RTX 3060 / T4 | 8GB | ~$0.30/hora |
| LLM reranker (Llama 70B) | A100 | 40GB | ~$2/hora |
| Two-Tower training | RTX 3080 / T4 | 10GB | ~$0.50/hora |

Para o caso de uso atual (recomendação pessoal, 16k jogos), **Opção 1 + Opção 2** rodam numa GPU de consumidor comum ou numa instância spot barata. Não precisa de infraestrutura séria.

---

## Descartado / On hold

| Iniciativa | Motivo |
|------------|--------|
| Collaborative filtering (outros usuários) | Precisa de volume de usuários para funcionar; retomar depois do AUTH-001 |
| RAWG API para catálogo externo | IGDB já cobre bem; RAWG como fonte adicional adiciona complexidade sem ganho claro agora |

---

## Princípios de produto

1. **Local-first** — enquanto for single-user, dados ficam em JSON local. Sem servidor desnecessário.
2. **Explicável** — recomendações sempre mostram o motivo. Caixa preta não.
3. **Sem ruído** — UI limpa. Cada feature adicionada deve remover complexidade percebida, não adicionar.
4. **Dados do usuário são do usuário** — export sempre disponível, sem lock-in.
