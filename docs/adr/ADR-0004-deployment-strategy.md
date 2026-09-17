# ADR-0004 — Stratégie de déploiement : Docker Compose (v1) → Kubernetes (v2)

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| Statut      | **Accepté**                         |
| Date        | 2026-06-29                          |
| Tags        | infra, devops, k8s, docker, iac     |

## Contexte

Le projet doit être déployable à deux niveaux de maturité :

- **v1 — Demo** : `docker compose up` sur n'importe quelle machine, zéro prérequis cloud.
- **v2 — Production-grade** : Kubernetes avec Helm charts, namespaces, RBAC, HPA, PodDisruptionBudget, pour un portfolio d'ingénierie complet.

La contrainte est que les deux versions doivent partager **la même configuration applicative** (variables d'environnement, noms de services, ports) pour éviter deux codebases divergentes.

## Principes retenus

### 1. Parité de configuration

Toutes les variables d'environnement sont déclarées dans un fichier `.env` unique à la racine. Docker Compose le lit nativement ; Kubernetes le consomme via un Secret/ConfigMap généré par un script.

```
.env                    ← source unique de vérité
├── docker-compose.yml  ← lit .env directement
└── infra/k8s/          ← généré par scripts/env-to-k8s.sh
    └── base/configmap.yaml
```

### 2. Noms de services identiques

Les services s'appellent `ingestion`, `rag-api`, `qdrant`, `postgres`, `redis`, `ollama`, `grafana`, `jaeger` dans les deux environnements. Les DNS internes Docker (`http://qdrant:6333`) sont identiques aux DNS k8s (`http://qdrant.rag-system.svc.cluster.local:6333` → résolu par `qdrant:6333` dans le même namespace).

### 3. Images Docker identiques

Les images buildées pour Docker Compose sont les mêmes que celles poussées sur GHCR pour k8s. Un seul `Dockerfile` multi-stage par service.

```
services/ingestion/Dockerfile  →  ghcr.io/user/rag-ingestion:sha
                                   ↑ utilisée dans compose ET k8s
```

### 4. Volumes → PVC

| Docker Compose        | Kubernetes v2             |
|-----------------------|---------------------------|
| `qdrant_data:/qdrant/storage` | PVC `qdrant-data` 10Gi |
| `postgres_data:/var/lib/postgresql` | PVC `postgres-data` 5Gi |
| `ollama_data:/root/.ollama` | PVC `ollama-models` 20Gi |
| `grafana_data:/var/lib/grafana` | PVC `grafana-data` 2Gi |

### 5. Observabilité identique

OTel Collector tourne dans les deux environnements. En v1 il envoie vers Jaeger local. En v2 il peut envoyer vers Jaeger ou un backend cloud (Grafana Tempo, Honeycomb) sans changer le code applicatif.

## Structure infra retenue

```
infra/
├── docker/
│   ├── docker-compose.yml          ← v1 complet
│   ├── docker-compose.override.yml ← dev hot-reload
│   └── .env.example
├── k8s/
│   ├── base/                       ← ressources communes (Kustomize)
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml
│   │   ├── configmap.yaml
│   │   ├── qdrant.yaml
│   │   ├── postgres.yaml
│   │   ├── redis.yaml
│   │   ├── ingestion.yaml
│   │   ├── rag-api.yaml
│   │   └── ...
│   └── overlays/
│       ├── dev/                    ← k3s local, 1 replica, debug
│       └── prod/                   ← cloud, HPA, PDB, TLS
└── helm/
    └── rag-system/                 ← chart Helm v2, packaging final
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
```

## Ordre de mise en place

Docker Compose (v1) d'abord, car il ne demande aucun accès cluster et permet
d'itérer vite sur l'application. Kustomize ensuite pour les manifests k8s de
base (dev/prod). Helm en dernier, une fois la structure Kustomize stabilisée,
pour offrir un chart installable en une commande (voir ADR-0008 et ADR-0009).

## Conséquences

- **Positif** : La v1 ne demande aucune connaissance k8s pour être lancée.
- **Positif** : La v2 réutilise 100% du code applicatif — seule l'infra change.
- **Négatif** : Maintenir deux systèmes de déploiement en parallèle pendant la transition.
- **Décision** : Docker Compose reste la référence de développement même en v2 — k8s est réservé au staging/prod.
