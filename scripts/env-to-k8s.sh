#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# scripts/env-to-k8s.sh — Convertit .env en ConfigMap Kubernetes
#
# Usage :
#   bash scripts/env-to-k8s.sh                    → affiche sur stdout
#   bash scripts/env-to-k8s.sh --apply            → kubectl apply direct
#   bash scripts/env-to-k8s.sh --out /tmp/cm.yaml → écrit dans un fichier
#
# Variables sensibles (PASSWORD, SECRET, KEY, TOKEN, DSN) sont
# automatiquement exclues — elles doivent aller dans un Secret k8s
# via scripts/k8s-secrets.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
NAMESPACE="${NAMESPACE:-rag-system}"
CM_NAME="${CM_NAME:-rag-config}"
APPLY=""
OUT_FILE=""

# ── Args ──────────────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --apply)          APPLY=1 ;;
    --out=*)          OUT_FILE="${arg#--out=}" ;;
    --out)            shift; OUT_FILE="${1:-}" ;;
    --namespace=*)    NAMESPACE="${arg#--namespace=}" ;;
    --name=*)         CM_NAME="${arg#--name=}" ;;
  esac
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[env-to-k8s]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }

# ── Vérifications ─────────────────────────────────────────────────────────────
[[ -f "$ENV_FILE" ]] || { echo "ERREUR : $ENV_FILE introuvable" >&2; exit 1; }

# ── Patterns de variables sensibles à exclure ─────────────────────────────────
SENSITIVE_PATTERN='PASSWORD|SECRET|TOKEN|KEY|DSN|CREDENTIALS|PRIVATE'

# ── Génération du ConfigMap ───────────────────────────────────────────────────
generate_configmap() {
  echo "# Généré automatiquement par scripts/env-to-k8s.sh"
  echo "# Source : $ENV_FILE · $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "# NE PAS COMMITER ce fichier s'il contient des valeurs sensibles"
  echo ""
  echo "apiVersion: v1"
  echo "kind: ConfigMap"
  echo "metadata:"
  echo "  name: $CM_NAME"
  echo "  namespace: $NAMESPACE"
  echo "  labels:"
  echo "    app.kubernetes.io/part-of: rag-system"
  echo "    app.kubernetes.io/managed-by: env-to-k8s"
  echo "data:"

  local excluded=0
  local included=0

  while IFS= read -r line || [[ -n "$line" ]]; do
    # Ignore commentaires et lignes vides
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line// }" ]] && continue

    # Extrait KEY=VALUE
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      key="${BASH_REMATCH[1]}"
      val="${BASH_REMATCH[2]}"

      # Exclut les variables sensibles
      if echo "$key" | grep -qiE "$SENSITIVE_PATTERN"; then
        warn "Exclu (sensible) : $key"
        excluded=$((excluded + 1))
        continue
      fi

      # Retire les guillemets optionnels autour de la valeur
      val="${val#\"}" ; val="${val%\"}"
      val="${val#\'}" ; val="${val%\'}"

      echo "  $key: $(printf '%q' "$val" | sed "s/^'//;s/'$//")"
      included=$((included + 1))
    fi
  done < "$ENV_FILE"

  log "$included variables incluses, $excluded exclues (sensibles → scripts/k8s-secrets.sh)"
}

# ── Sortie ────────────────────────────────────────────────────────────────────
YAML="$(generate_configmap)"

if [[ -n "$OUT_FILE" ]]; then
  echo "$YAML" > "$OUT_FILE"
  log "Écrit dans $OUT_FILE"
elif [[ -n "$APPLY" ]]; then
  echo "$YAML" | kubectl apply -f -
  log "ConfigMap $CM_NAME appliqué dans le namespace $NAMESPACE"
else
  echo "$YAML"
fi
