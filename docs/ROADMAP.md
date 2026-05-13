# Product Roadmap — Gamelog

> Documento de planejamento de produto. Atualizado conforme features são planejadas ou priorizadas.
> Última atualização: 2026-05-13

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
