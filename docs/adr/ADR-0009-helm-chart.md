# ADR-0009 — Chart Helm : structure, values et hooks

| Champ       | Valeur                              |
|-------------|--------------------------------------|
| Statut      | **Accepté**                          |
| Date        | 2026-06-30                           |
| Tags        | helm, k8s, packaging, devops         |

## Contexte

Le chart Helm est la couche de packaging final au-dessus de Kustomize. Il permet :
- `helm install rag-system ./helm/rag-system` — déploiement en une commande
- `helm upgrade` avec rollback automatique (`--atomic`)
- Configuration centralisée dans `values.yaml`
- Séparation claire entre valeurs par défaut et overrides utilisateur

## Décisions structurelles

### 1. Pas de sous-charts pour les dépendances

Qdrant, PostgreSQL, Redis et Ollama auraient pu être importés comme dépendances Helm (`Chart.yaml dependencies`). Ce n'est pas retenu pour la v1 car :
- Les charts communautaires (Bitnami Postgres, etc.) ont des conventions incompatibles avec nos ConfigMaps
- Cela crée des `values.yaml` profondément imbriqués difficiles à lire
- On garde le contrôle total sur les StatefulSets pour les PVC et les probes

### 2. Structure `values.yaml`

```yaml
global:
  imageRegistry: ghcr.io/ton-user
  imageTag: latest
  imagePullPolicy: IfNotPresent

ingestion:
  replicaCount: 2
  image: { repository: rag-ingestion, tag: "" }
  resources: { requests: {...}, limits: {...} }

ragApi:
  replicaCount: 2
  hpa: { enabled: true, minReplicas: 2, maxReplicas: 8 }

qdrant:
  persistence: { size: 10Gi }

ollama:
  model: llama3.2:3b
  embedModel: nomic-embed-text
  gpu: { enabled: false, nodeSelector: { gpu: "true" } }

observability:
  otel:   { enabled: true,  endpoint: "http://otel-collector:4317" }
  jaeger: { enabled: true }
  grafana: { enabled: true, adminPassword: "change-me" }

ingress:
  enabled: false
  host: ""
  tls: { enabled: false }
```

### 3. Hooks Helm

Un hook `pre-install` et `pre-upgrade` crée la collection Qdrant et joue les migrations PostgreSQL avant le déploiement des pods applicatifs.

### 4. Tests Helm

`helm test rag-system` lance un pod éphémère qui :
1. Appelle `GET /health` sur ingestion et rag-api
2. Poste un document texte minimal via `/ingest`
3. Attend le statut `completed`
4. Pose une question via `/query` et vérifie la réponse SSE

## Conséquences

- **Positif** : `helm lint` + `helm template` validables en CI sans cluster.
- **Positif** : `helm upgrade --atomic` rollback automatique si le rollout échoue.
- **Négatif** : Un seul chart — pas de composition Helm fine par composant. Acceptable pour v1.
- **Révision** : Si le projet grandit, envisager un umbrella chart avec sous-charts indépendants.
