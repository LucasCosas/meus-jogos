# Design Brief — GameLog App

## O que é o app

GameLog é um catálogo pessoal de jogos. O usuário registra os jogos que jogou, dá notas, acompanha o backlog (jogos que quer jogar), tem uma wishlist e recebe recomendações personalizadas baseadas no seu gosto. É um app de uso pessoal e frequente — quase um diário de jogos.

---

## Personalidade e vibe

**O que queremos:**
- Leve, clarinho, arejado — o oposto do dark mode típico do mundo gamer
- Playful e divertido — parece um hobby, não uma ferramenta corporativa
- Caloroso — como uma estante de jogos bem organizada, não um dashboard frio
- Tem personalidade própria — pode ter pequenos detalhes charming (ícones expressivos, micro-animações, tipografia com caráter)

**Referências de vibe (não de interface):**
- A sensação de um caderno de anotações bem decorado
- Letterboxd — mas mais colorido e menos minimalista
- Notion com mais alegria
- Um card game físico bem impresso
- O charme visual de um jogo indie com boa arte (Hades, Disco Elysium, Hollow Knight têm UIs lindas)

**O que NÃO queremos:**
- Dark mode com neon (muito clichê gamer)
- Estilo esportivo / esports (muito agressivo)
- Corporativo / SaaS genérico
- Minimalismo excessivo que apaga a personalidade

---

## Direção visual

### Paleta de cores
- **Background:** branco ou off-white muito claro (não cinza frio)
- **Superfícies:** tons creme, bege clarinho, ou lavanda muito suave
- **Acento primário:** algo inesperado e divertido — laranja vibrante, coral, verde-água, lilás saturado, ou amarelo mostarda. Não azul padrão.
- **Acento secundário:** complementar ao primário, mais suave
- **Texto:** marrom escuro ou quase-preto (não preto puro, não cinza frio)
- **Danger/erro:** vermelho coral (não vermelho duro)
- **Sucesso:** verde salva (não verde néon)

Paleta sugerida como ponto de partida (pode mudar totalmente):
- Background: `#FAFAF7` (quase branco com toque amarelado)
- Superfície de card: `#FFFFFF` com sombra suave
- Acento: `#FF6B35` (laranja vibrante) ou `#7C3AED` (violeta) ou `#059669` (verde esmeralda)
- Texto principal: `#1C1917`

### Tipografia
- **Display / títulos:** fonte com caráter — algo como DM Serif Display, Playfair Display, Fraunces, ou uma sans-serif com personalidade como Syne, Plus Jakarta Sans, ou Nunito
- **Corpo:** legível, amigável — Inter, DM Sans, ou Nunito
- **Mistura:** considerar usar serif para títulos de jogos e sans para metadados — cria hierarquia rica
- **Tamanhos generosos:** cards com título em destaque real

### Cards
Os cards de jogos são o elemento central da interface. Devem parecer colecionáveis — como se cada jogo fosse um item especial na sua estante.

**Card de jogo (catálogo):**
- Borda levemente arredondada (12–16px)
- Sombra suave (não flat, não neumorphism exagerado)
- Título em destaque com tipografia expressiva
- Nota com estrelas ou sistema visual próprio (não apenas número)
- Tags de gênero coloridas por categoria
- Plataforma com ícone/badge
- Hover: leve elevação ou mudança de borda colorida

**Card de recomendação:**
- Similar ao card de jogo mas com ranking (#1, #2...) em badge
- Chips de sinal (genre fit, IGDB score, etc.) devem parecer badges divertidos, não pills técnicos

### Navegação
- Tabs horizontais no topo
- Estilo: pills/chips com ícones + texto, não tabs de linha
- Tab ativa: cor de fundo preenchida com acento, cantos arredondados
- Considerar ícones expressivos para cada tab:
  - 📚 Catálogo
  - 🎯 Backlog
  - 💾 Wishlist
  - ✨ Recomendações
  - 👤 Perfil

### Formulários e modais
- Modal de adicionar/editar jogo: deve parecer um formulário de colecionador, não um form de RH
- Rating com estrelas grandes e interativas (não radio buttons numéricos)
- Seleção de gênero com chips coloridos
- Fundo do modal: overlay com blur suave

### Estados e feedback
- Toast notifications: pill flutuante com ícone, não retângulo genérico
- Estado vazio: ilustração simples (não só texto), com CTA amigável
- Loading: skeleton animado nos cards

---

## Estrutura de páginas

### 1. Catálogo (página inicial)
- Toolbar com busca, filtros de gênero/plataforma/ordenação
- Grid de cards responsivo (3–4 colunas desktop, 1–2 mobile)
- Botão "+ Adicionar Jogo" em destaque no canto superior direito
- Botões de ação rápida: "⭐ Avaliar" e "🕹 Quanto Joguei"

### 2. Backlog
- Mesma estrutura de grid
- Card com botões "✅ Já joguei" e "+ Wishlist"
- Filtros: busca, gênero/tag, plataforma, ordenação
- Contador de jogos no backlog

### 3. Wishlist
- Lista vertical de cards (não grid) — estilo "fila de espera"
- Botão "▶ Comecei" (move para catálogo) e "Remover"
- Estado vazio: charming, convida a ir explorar as Recomendações

### 4. Recomendações
- Tabs internas: "Por Gênero / Subgênero" e "Parecido com..."
- Seletor de gênero/subgênero com optgroups estilizados
- Botões de modo: Balanceado / Hidden Gems / Top Rated
- Painel de pesos (sliders) — pode ser colapsável com ícone ⚙
- Lista rankeada de recomendações com signal chips coloridos
- Cada card tem: rank badge (#1), título, tags, plataformas, e chips de motivo (🎭 Gênero +8.4, ⚔ Soulslike, 🎯 IGDB 91)

### 5. Perfil & Stats
- Header com stats em destaque: X jogos, Y% zerados, Z horas estimadas
- Gráfico de afinidade por gênero (barras horizontais coloridas)
- Top 5 jogos por tempo
- Gráfico de horas por plataforma
- Botão de configurar plataformas/assinaturas

---

## Componentes-chave a projetar

1. **Game Card** (catálogo e backlog) — o mais importante
2. **Recommendation Card** com rank badge e signal chips
3. **Navbar** com tabs estilizadas
4. **Modal** de adicionar/editar jogo com rating por estrelas
5. **Rating input** (estrelas grandes e interativas)
6. **Genre chips** (seleção múltipla colorida)
7. **Toast notification**
8. **Painel de pesos** com sliders estilizados
9. **Stat boxes** no perfil
10. **Empty states** com ilustração

---

## Detalhes de comportamento (para referência)

- Rating: escala de 1–10 (internamente), exibido como 1–5 estrelas
- Playtime: little / medium / much / completed (Pouco / Médio / Muito / Zerado)
- Plataformas suportadas: PlayStation 5, PlayStation 4, Xbox Series X|S, Nintendo Switch, PC (Microsoft Windows), Mac, iOS, Android
- Gêneros: tags livres, o usuário pode criar os seus
- Subgêneros especiais: Soulslike, Metroidvania, Roguelite, Roguelike

---

## O que entregar

Telas em alta fidelidade para:
1. Catálogo (com cards preenchidos — use jogos reais como Elden Ring, Hollow Knight, God of War)
2. Modal de adicionar jogo (aberto)
3. Recomendações (com lista populada)
4. Perfil & Stats
5. Versão mobile do Catálogo

Design system com:
- Paleta de cores com tokens nomeados
- Escala tipográfica
- Variantes do Game Card (normal, hover, com nota, sem nota)
- Estados dos botões (default, hover, active, disabled)
