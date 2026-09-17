#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/k8s-deploy.sh — Déploie le RAG System sur Kubernetes
#
# Usage :
#   bash scripts/k8s-deploy.sh dev    → overlay dev (k3s local)
#   bash scripts/k8s-deploy.sh prod   → overlay prod (cloud)
#   bash scripts/k8s-deploy.sh dev --dry-run   → affiche le YAML sans appliquer
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

OVERLAY="${1:-dev}"
DRY_RUN="${2:-}"
K8S_DIR="infra/k8s"

GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
BOLD='\033[1m'; NC='\033[0m'

log()    { echo -e "${GREEN}[k8s]${NC} $*"; }
info()   { echo -e "${BLUE}[k8s]${NC} $*"; }
warn()   { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()  { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
header() { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}\n"; }

# ── Vérifications ──────────────────────────────────────────────────────────────
command -v kubectl   >/dev/null 2>&1 || error "kubectl non trouvé"
command -v kustomize >/dev/null 2>&1 || error "kustomize non trouvé (brew install kustomize)"

[[ -d "$K8S_DIR/overlays/$OVERLAY" ]] || error "Overlay '$OVERLAY' inexistant dans $K8S_DIR/overlays/"

OVERLAY_PATH="$K8S_DIR/overlays/$OVERLAY"

# ── Dry-run : affiche le YAML généré ──────────────────────────────────────────
if [[ "$DRY_RUN" == "--dry-run" ]]; then
  header "YAML généré par kustomize (overlay=$OVERLAY)"
  kustomize build "$OVERLAY_PATH"
  echo -e "\n${YELLOW}Mode dry-run : rien n'a été appliqué.${NC}"
  exit 0
fi

# ── Confirmation pour prod ─────────────────────────────────────────────────────
if [[ "$OVERLAY" == "prod" ]]; then
  warn "⚠️  Déploiement en PRODUCTION"
  read -rp "Confirmer ? [y/N] " confirm
  [[ "$confirm" == "y" || "$confirm" == "Y" ]] || { log "Annulé."; exit 0; }
fi

# ── Namespace ─────────────────────────────────────────────────────────────────
header "Namespace"
kubectl apply -f "$K8S_DIR/base/namespace.yaml"

# ── Secrets ───────────────────────────────────────────────────────────────────
header "Secrets"
if kubectl get secret rag-secrets -n rag-system &>/dev/null; then
  log "Secret rag-secrets déjà présent"
else
  warn "Secret absent — génération depuis .env"
  bash scripts/k8s-secrets.sh "$OVERLAY"
fi

# ── Déploiement Kustomize ─────────────────────────────────────────────────────
header "Déploiement (overlay=$OVERLAY)"
log "kustomize build $OVERLAY_PATH | kubectl apply -f -"
kustomize build "$OVERLAY_PATH" | kubectl apply -f -

# ── Attente rollout ───────────────────────────────────────────────────────────
header "Rollout"
DEPLOYMENTS=(rag-api ingestion frontend ollama)
for dep in "${DEPLOYMENTS[@]}"; do
  log "Attente rollout $dep…"
  kubectl rollout status deployment/"$dep" -n rag-system --timeout=300s || \
    warn "$dep rollout non terminé dans les délais — vérifier : kubectl describe pod -n rag-system -l app=$dep"
done

# ── Résumé ────────────────────────────────────────────────────────────────────
header "État du déploiement"
kubectl get pods -n rag-system -o wide

echo ""
log "Déploiement terminé ✓"
log "Logs : kubectl logs -n rag-system -l app=rag-api -f"
log "Port-forward : kubectl port-forward -n rag-system svc/frontend 3000:3000"
