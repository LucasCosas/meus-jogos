#!/bin/bash
# Mostra o status de todos os processos e arquivos do pipeline

TOTAL=13587

pct() { python3 -c "print(f'{int($1/$2*100)}%')" 2>/dev/null || echo "?%"; }
count_with() { python3 -c "import json; d=json.load(open('$1')); print(sum(1 for v in d.values() if v))" 2>/dev/null || echo "0"; }
count_all()  { python3 -c "import json; d=json.load(open('$1')); print(len(d))" 2>/dev/null || echo "0"; }

echo ""
echo "══════════════════════════════════════════"
echo "   Pipeline Status"
echo "══════════════════════════════════════════"

# ── Processos rodando ─────────────────────────────────────────────────────────
echo ""
echo "▶ Processos ativos:"
STEAM_PROC=$(pgrep -f fetch_steam_tags | wc -l | tr -d ' ')
WIKI_PROC=$(pgrep -f fetch_wiki | wc -l | tr -d ' ')
ENRICH_PROC=$(pgrep -f enrich_descriptions | wc -l | tr -d ' ')
OLLAMA_PROC=$(pgrep -f "ollama serve" | wc -l | tr -d ' ')

[ "$STEAM_PROC"   -gt 0 ] && echo "  🔄 fetch_steam_tags.py    rodando" || echo "  ✓  fetch_steam_tags.py    parado"
[ "$WIKI_PROC"    -gt 0 ] && echo "  🔄 fetch_wiki.py          rodando" || echo "  ✓  fetch_wiki.py          parado"
[ "$ENRICH_PROC"  -gt 0 ] && echo "  🔄 enrich_descriptions.py rodando" || echo "  ✓  enrich_descriptions.py parado"
[ "$OLLAMA_PROC"  -gt 0 ] && echo "  🟢 Ollama serve           ativo"   || echo "  ⚪  Ollama serve           inativo"

# ── Arquivos gerados ──────────────────────────────────────────────────────────
echo ""
echo "▶ Dados coletados:"

if [ -f steam_tags.json ]; then
  ALL=$(count_all steam_tags.json)
  WITH=$(count_with steam_tags.json)
  echo "  steam_tags.json       $ALL/$TOTAL entradas  |  $WITH com tags  ($(pct $ALL $TOTAL))"
else
  echo "  steam_tags.json       não existe ainda"
fi

if [ -f wiki_summaries.json ]; then
  ALL=$(count_all wiki_summaries.json)
  WITH=$(count_with wiki_summaries.json)
  echo "  wiki_summaries.json   $ALL/$TOTAL entradas  |  $WITH com texto  ($(pct $ALL $TOTAL))"
else
  echo "  wiki_summaries.json   não existe ainda"
fi

if [ -f enriched_descriptions.json ]; then
  ALL=$(count_all enriched_descriptions.json)
  WITH=$(count_with enriched_descriptions.json)
  echo "  enriched_descriptions $ALL/$TOTAL entradas  |  $WITH com descrição  ($(pct $ALL $TOTAL))"
else
  echo "  enriched_descriptions não existe ainda"
fi

# ── Ollama / modelo ───────────────────────────────────────────────────────────
echo ""
echo "▶ Ollama:"
MODELS=$(curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)
    models=d.get('models',[])
    if models:
        for m in models: print(f'  ✓  {m[\"name\"]}  ({m[\"size\"]/1e9:.1f} GB)')
    else:
        print('  ⏳ modelo ainda baixando...')
except:
    print('  ⚪  servidor não está rodando')
" 2>/dev/null)
echo "$MODELS"

# ── Próximo passo ─────────────────────────────────────────────────────────────
echo ""
echo "▶ Próximo passo:"
STEAM_DONE=$([ -f steam_tags.json ] && [ "$(count_all steam_tags.json)" -ge "$TOTAL" ] && echo 1 || echo 0)
WIKI_DONE=$([ -f wiki_summaries.json ] && [ "$(count_all wiki_summaries.json)" -ge "$TOTAL" ] && echo 1 || echo 0)
ENRICH_DONE=$([ -f enriched_descriptions.json ] && [ "$(count_all enriched_descriptions.json)" -ge 1000 ] && echo 1 || echo 0)
MODEL_READY=$(curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(1 if d.get('models') else 0)" 2>/dev/null || echo 0)

if [ "$STEAM_DONE" = "1" ] && [ "$WIKI_DONE" = "1" ] && [ "$ENRICH_PROC" = "0" ] && [ "$MODEL_READY" = "0" ]; then
  echo "  → Steam e Wiki prontos! Inicia o Ollama e rode:"
  echo "    /Applications/Ollama.app/Contents/Resources/ollama serve &"
  echo "    python3 archive/enrich_descriptions.py"
elif [ "$ENRICH_DONE" = "1" ] || ([ "$STEAM_DONE" = "1" ] && [ "$WIKI_DONE" = "1" ] && [ "$ENRICH_PROC" = "0" ]); then
  echo "  → Tudo pronto! Regenera embeddings e clusters:"
  echo "    python3 archive/generate_embeddings.py"
  echo "    python3 archive/cluster_games.py"
elif [ "$STEAM_PROC" -gt 0 ] || [ "$WIKI_PROC" -gt 0 ] || [ "$ENRICH_PROC" -gt 0 ]; then
  echo "  → Aguarda os processos terminarem, então rode este script de novo."
else
  echo "  → Tudo parado. Verifica os logs ou reinicia os processos necessários."
fi

echo ""
echo "══════════════════════════════════════════"
