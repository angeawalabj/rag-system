#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/stop.sh — Arrête proprement le système RAG
# Usage :
#   bash scripts/stop.sh           # arrête les conteneurs, garde les volumes
#   bash scripts/stop.sh --clean   # arrête + supprime tous les volumes (reset complet)
#   bash scripts/stop.sh --demo    # alias de --clean (fin de demo)
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

COMPOSE_FILE="infra/docker/docker-compose.yml"
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${GREEN}[RAG]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

MODE="${1:-}"

if [[ "$MODE" == "--clean" || "$MODE" == "--demo" ]]; then
  warn "Mode --clean : suppression de TOUS les volumes (données perdues)"
  read -rp "Confirmer ? [y/N] " confirm
  if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    log "Annulé."
    exit 0
  fi
  docker compose -f "$COMPOSE_FILE" down --volumes --remove-orphans
  log "Conteneurs et volumes supprimés."
else
  docker compose -f "$COMPOSE_FILE" down --remove-orphans
  log "Conteneurs arrêtés. Volumes conservés."
  log "Pour nettoyer complètement : bash scripts/stop.sh --clean"
fi

echo -e "\n${BOLD}Bye 👋${NC}"
