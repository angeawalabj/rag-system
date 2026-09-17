#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/k8s-secrets.sh — Génère le Secret Kubernetes depuis .env
#
# Usage :
#   bash scripts/k8s-secrets.sh [overlay]
#   bash scripts/k8s-secrets.sh dev   → applique dans overlays/dev
#   bash scripts/k8s-secrets.sh prod  → applique dans overlays/prod
#
# Le secret est JAMAIS commité — il est généré à la volée depuis .env
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
OVERLAY="${1:-dev}"
NAMESPACE="rag-system"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[k8s-secrets]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ── Vérifications ──────────────────────────────────────────────────────────────
[[ -f "$ENV_FILE" ]] || { echo "ERREUR : $ENV_FILE introuvable — copier .env.example"; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "ERREUR : kubectl non trouvé"; exit 1; }

# ── Chargement du .env ────────────────────────────────────────────────────────
# shellcheck source=../.env
set -a
source "$ENV_FILE"
set +a

# ── Vérification des valeurs obligatoires ─────────────────────────────────────
REQUIRED=(POSTGRES_USER POSTGRES_PASSWORD GRAFANA_PASSWORD)
for var in "${REQUIRED[@]}"; do
  [[ -v "$var" ]] || { echo "ERREUR : $var non défini dans $ENV_FILE"; exit 1; }
  [[ "${!var}" != *"CHANGE-ME"* ]] || warn "$var contient encore 'CHANGE-ME' — à modifier avant la prod"
done

# ── Génération du Secret ───────────────────────────────────────────────────────
log "Génération du Secret rag-secrets (overlay=$OVERLAY)"

POSTGRES_DSN="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB:-ragdb}"

kubectl create secret generic rag-secrets \
  --namespace="${NAMESPACE}" \
  --from-literal="POSTGRES_USER=${POSTGRES_USER}" \
  --from-literal="POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
  --from-literal="POSTGRES_DSN=${POSTGRES_DSN}" \
  --from-literal="GRAFANA_USER=${GRAFANA_USER:-admin}" \
  --from-literal="GRAFANA_PASSWORD=${GRAFANA_PASSWORD}" \
  --dry-run=client -o yaml | kubectl apply -f -

log "Secret appliqué dans le namespace ${NAMESPACE}"
log "Vérification : kubectl get secret rag-secrets -n ${NAMESPACE}"
