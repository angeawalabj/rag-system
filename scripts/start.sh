#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/start.sh — Démarre le système RAG complet (v1 Docker Compose)
# Usage : bash scripts/start.sh [--fast]
#   --fast  : ne repull pas les images si elles existent déjà
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

COMPOSE_FILE="infra/docker/docker-compose.yml"
ENV_FILE=".env"

# ── Couleurs ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'; BOLD='\033[1m'

log()    { echo -e "${GREEN}[RAG]${NC} $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
header() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }

# ── Vérifications prérequis ───────────────────────────────────────────────────
header "Vérification des prérequis"

command -v docker  >/dev/null 2>&1 || error "Docker non trouvé"
command -v docker compose >/dev/null 2>&1 || error "docker compose non trouvé (Docker >= 24 requis)"

# RAM disponible (Linux)
if [[ "$(uname)" == "Linux" ]]; then
  AVAIL_GB=$(awk '/MemAvailable/ { printf "%.0f", $2/1024/1024 }' /proc/meminfo)
  if (( AVAIL_GB < 6 )); then
    warn "RAM disponible : ${AVAIL_GB} GB — recommandé ≥ 8 GB pour Ollama + services"
  else
    log "RAM disponible : ${AVAIL_GB} GB ✓"
  fi
fi

# ── Fichier .env ──────────────────────────────────────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  warn ".env absent — copie depuis .env.example"
  cp .env.example .env
  warn "⚠️  Modifie .env (mots de passe !) avant de déployer en prod"
fi

# ── Build images locales ──────────────────────────────────────────────────────
header "Build des images Docker"

if [[ "${1:-}" != "--fast" ]]; then
  docker compose -f "$COMPOSE_FILE" build --parallel
else
  log "Mode --fast : skip build si images présentes"
fi

# ── Démarrage des services d'infrastructure ────────────────────────────────────
header "Démarrage infrastructure (Qdrant, PostgreSQL, Redis)"

docker compose -f "$COMPOSE_FILE" up -d qdrant postgres redis

log "Attente que l'infrastructure soit prête..."
sleep 5

# ── Démarrage Ollama ──────────────────────────────────────────────────────────
header "Démarrage Ollama + pull des modèles"

docker compose -f "$COMPOSE_FILE" up -d ollama
log "Pull des modèles (peut prendre 5-15 min au premier lancement)..."
docker compose -f "$COMPOSE_FILE" run --rm ollama-init

# ── Démarrage services applicatifs ────────────────────────────────────────────
header "Démarrage services applicatifs"

docker compose -f "$COMPOSE_FILE" up -d ingestion rag-api frontend

# ── Observabilité ─────────────────────────────────────────────────────────────
header "Démarrage observabilité"

docker compose -f "$COMPOSE_FILE" up -d otel-collector jaeger prometheus grafana

# ── Vérification santé ────────────────────────────────────────────────────────
header "Vérification des healthchecks"

sleep 10

SERVICES=("ingestion:8001/health" "rag-api:8000/health")
for svc in "${SERVICES[@]}"; do
  name="${svc%%:*}"
  url="http://localhost:${svc#*:}"
  if curl -sf "$url" >/dev/null 2>&1; then
    log "$name ✓ ($url)"
  else
    warn "$name pas encore prêt — vérifier : docker compose -f $COMPOSE_FILE logs $name"
  fi
done

# ── Résumé ────────────────────────────────────────────────────────────────────
header "Système démarré 🚀"

cat << EOF
  Frontend       → http://localhost:3000
  RAG API        → http://localhost:8000/docs
  Ingestion API  → http://localhost:8001/docs
  Qdrant UI      → http://localhost:6333/dashboard
  Grafana        → http://localhost:3001  (admin/admin)
  Jaeger UI      → http://localhost:16686
  Prometheus     → http://localhost:9090

  Logs en direct : docker compose -f $COMPOSE_FILE logs -f
  Arrêt propre   : bash scripts/stop.sh
EOF
