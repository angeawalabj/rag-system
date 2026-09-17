#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/smoke-test.sh — Valide le pipeline d'ingestion end-to-end
# Usage : bash scripts/smoke-test.sh
# Prérequis : bash scripts/start.sh exécuté
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

API_BASE="${INGESTION_URL:-http://localhost:8001}"
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; NC='\033[0m'

pass() { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; FAILURES=$((FAILURES + 1)); }
info() { echo -e "${YELLOW}→${NC} $*"; }

FAILURES=0

echo -e "\n${BOLD}=== Smoke Tests — Ingestion Service ===${NC}\n"

# ── 1. Healthcheck ────────────────────────────────────────────────────────────
info "1. Healthcheck"
HEALTH=$(curl -sf "$API_BASE/health" 2>/dev/null || echo "FAIL")
if echo "$HEALTH" | grep -q '"ok"'; then
  pass "GET /health → ok"
else
  fail "GET /health — réponse inattendue : $HEALTH"
fi

# ── 2. Upload d'un fichier TXT de test ────────────────────────────────────────
info "2. Upload document TXT"
TMP_FILE=$(mktemp /tmp/rag-test-XXXX.txt)
cat > "$TMP_FILE" << 'DOC'
# Rapport Q1 2026 — Résumé exécutif

Le chiffre d'affaires du premier trimestre 2026 s'élève à 4,2 millions d'euros,
en hausse de 18% par rapport au Q1 2025. Cette croissance est portée par le
segment cloud qui représente désormais 62% des revenus totaux.

## Points clés

- Nouveaux clients : 47 comptes Enterprise signés en Q1
- Rétention : 94% de taux de renouvellement
- EBITDA : 0,8 M€ soit 19% de marge
- Effectifs : +12 recrutements, équipe totale 89 personnes

## Perspectives Q2

L'objectif Q2 est un CA de 4,8 M€ avec un focus sur l'expansion internationale,
notamment sur les marchés allemand et néerlandais.
DOC

INGEST_RESP=$(curl -sf -X POST "$API_BASE/ingest" \
  -F "file=@$TMP_FILE;type=text/plain" \
  -F "collection=smoke-test" 2>/dev/null || echo "FAIL")

rm -f "$TMP_FILE"

if echo "$INGEST_RESP" | grep -q '"doc_id"'; then
  DOC_ID=$(echo "$INGEST_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['doc_id'])")
  pass "POST /ingest → doc_id=$DOC_ID"
else
  fail "POST /ingest — réponse : $INGEST_RESP"
  exit 1
fi

# ── 3. Polling statut jusqu'à completed ───────────────────────────────────────
info "3. Polling statut d'ingestion (timeout 120s)"
TIMEOUT=120
ELAPSED=0
STATUS=""

while [[ $ELAPSED -lt $TIMEOUT ]]; do
  STATUS_RESP=$(curl -sf "$API_BASE/ingest/$DOC_ID" 2>/dev/null || echo '{"status":"error"}')
  STATUS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || echo "error")

  case "$STATUS" in
    completed)
      CHUNKS=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('chunk_count', 0))" 2>/dev/null || echo "?")
      pass "Ingestion completed — chunks=$CHUNKS"
      break
      ;;
    failed)
      ERR=$(echo "$STATUS_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','?'))" 2>/dev/null || echo "?")
      fail "Ingestion failed : $ERR"
      break
      ;;
    pending|processing)
      echo -n "."
      sleep 5
      ELAPSED=$((ELAPSED + 5))
      ;;
    *)
      fail "Statut inattendu : $STATUS"
      break
      ;;
  esac
done

if [[ $ELAPSED -ge $TIMEOUT ]]; then
  fail "Timeout — ingestion toujours en statut '$STATUS' après ${TIMEOUT}s"
fi

# ── 4. Liste des documents ────────────────────────────────────────────────────
info "4. GET /documents?collection=smoke-test"
DOCS=$(curl -sf "$API_BASE/documents?collection=smoke-test" 2>/dev/null || echo "FAIL")
if echo "$DOCS" | grep -q '"total"'; then
  TOTAL=$(echo "$DOCS" | python3 -c "import sys,json; print(json.load(sys.stdin)['total'])" 2>/dev/null || echo "?")
  pass "GET /documents → total=$TOTAL"
else
  fail "GET /documents — réponse : $DOCS"
fi

# ── 5. Métriques Prometheus ───────────────────────────────────────────────────
info "5. GET /metrics (Prometheus)"
METRICS=$(curl -sf "$API_BASE/metrics" 2>/dev/null || echo "FAIL")
if echo "$METRICS" | grep -q "rag_ingestion_documents_total"; then
  pass "GET /metrics → métriques présentes"
else
  fail "GET /metrics — métriques absentes"
fi

# ── Résumé ────────────────────────────────────────────────────────────────────
echo ""
if [[ $FAILURES -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}Tous les tests passent ✓${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}$FAILURES test(s) échoué(s) ✗${NC}"
  exit 1
fi
