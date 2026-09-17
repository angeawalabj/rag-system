# Génère le ConfigMap postgres-init-scripts depuis le fichier SQL existant.
#
# Ce fichier sert de référence : le vrai ConfigMap est généré par
# `kustomize` via `configMapGenerator` dans kustomization.yaml,
# qui lit directement infra/docker/init-db/01-schema.sql.
#
# Évite de dupliquer le schéma SQL entre Docker Compose et Kubernetes —
# une seule source de vérité (ADR-0004, principe de parité de configuration).
