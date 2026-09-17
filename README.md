# RAG System — Pipeline RAG (Retrieval-Augmented Generation) avec Qdrant, Ollama et FastAPI

Système de **retrieval-augmented generation (RAG)** en microservices : ingestion de documents (PDF, Markdown, TXT, URL), indexation vectorielle dans **Qdrant**, et génération de réponses **streamées en temps réel (SSE)** par un LLM local servi via **Ollama**.

## Présentation

Ce projet est une démo/portfolio illustrant une architecture RAG de bout en bout, pensée pour un déploiement local (Docker Compose) ou Kubernetes (Helm/Kustomize fournis dans `infra/`). Il se compose de trois services applicatifs — un frontend de chat, une API de requêtage RAG et un service d'ingestion — appuyés sur Qdrant (base vectorielle), PostgreSQL (métadonnées documents), Redis (cache de réponses + file de jobs RQ) et Ollama (embeddings et génération LLM, en local, sans dépendance à une API cloud). L'ensemble est instrumenté avec OpenTelemetry, Prometheus, Jaeger et Grafana pour l'observabilité.

## Architecture / Services

| Service | Technologie | Rôle |
|---|---|---|
| `services/frontend` | Next.js 14.2.5 (App Router), React 18, TypeScript, Tailwind CSS | Interface de chat : pose de questions, affichage des réponses en streaming token par token, panneau de dépôt de documents (drag & drop) avec suivi de statut d'ingestion |
| `services/api` | FastAPI, `sse-starlette` | Reçoit une question, l'embed via Ollama, recherche les chunks pertinents dans Qdrant (`AsyncQdrantClient`), construit un prompt augmenté et streame la réponse du LLM en Server-Sent Events ; cache les réponses dans Redis |
| `services/ingestion` | FastAPI, `python-multipart`, RQ (Redis Queue) | Reçoit un upload de document, le découpe en chunks, les embed via Ollama et les indexe dans Qdrant ; traitement asynchrone via une file RQ, statut persisté en PostgreSQL |

## Fonctionnalités

- **Génération en streaming** : réponses du LLM diffusées token par token au client via Server-Sent Events (`sse-starlette` côté API, lecture de flux `ReadableStream` côté frontend), avec un dernier événement listant les sources citées.
- **Base vectorielle Qdrant** : embeddings de 768 dimensions (modèle `nomic-embed-text`), distance cosinus, filtrage par collection via les `Filter`/`FieldCondition` de Qdrant.
- **LLM et embeddings 100 % locaux via Ollama** : `nomic-embed-text` pour les embeddings, `llama3.2:3b` par défaut pour la génération (endpoint OpenAI-compatible `/v1/chat/completions`), configurables par variables d'environnement.
- **Prompt RAG strict** : le système est instruit de répondre uniquement à partir du contexte fourni, de citer ses sources sous forme `[1]`, `[2]`… et d'indiquer explicitement quand l'information est absente des documents.
- **Ingestion multi-format** : loaders dédiés pour PDF (`pypdf`, extraction page par page avec numéro de page conservé), Markdown, TXT et pages web (`BeautifulSoup`, nettoyage du HTML non pertinent).
- **Chunking configurable** : découpage récursif (`RecursiveCharacterTextSplitter` de LangChain), taille de chunk et overlap paramétrables (512 / 64 caractères par défaut).
- **Ingestion asynchrone** : upload immédiat (202 Accepted) puis traitement en arrière-plan via une file RQ/Redis, avec suivi de statut (`pending` → `processing` → `completed`/`failed`) interrogeable par l'API et pollé par le frontend.
- **Cache de réponses Redis** : les réponses complètes (tokens + sources) sont mises en cache par clé `question + collection + top_k` (TTL configurable), avec invalidation par collection.
- **Observabilité complète** : traces distribuées OpenTelemetry (export OTLP vers Jaeger), métriques Prometheus (latence de requête, chunks retournés, jobs en attente…) et dashboards Grafana.
- **Endpoints de service standard** : `/health` (vérifie Qdrant/Redis) et `/metrics` (Prometheus) exposés par l'API et le service d'ingestion.

## Structure du projet

```
rag-system/
├── services/
│   ├── frontend/            # Next.js 14 — interface de chat (App Router)
│   │   ├── app/              # routes (page.tsx, chat/)
│   │   ├── components/       # ChatWindow, MessageBubble, QueryInput, SourceCard, UploadPanel
│   │   └── lib/               # client API (fetch SSE, upload, polling)
│   │
│   ├── api/                  # FastAPI — requêtage RAG (retrieve → augment → generate)
│   │   └── src/
│   │       ├── main.py        # routes /query (SSE), /collections, /cache, /health, /metrics
│   │       ├── retriever.py   # embedding de la question + recherche Qdrant
│   │       ├── generator.py   # construction du prompt + streaming Ollama
│   │       └── cache.py       # cache Redis des réponses
│   │
│   └── ingestion/            # FastAPI — pipeline d'ingestion documentaire
│       └── src/
│           ├── main.py        # routes /ingest, /ingest/{id}, /documents, /health
│           ├── loaders.py     # PDF / Markdown / TXT / URL
│           ├── embedder.py    # client d'embedding Ollama
│           └── pipeline.py    # chunking + embedding + upsert Qdrant
│
├── infra/
│   ├── docker/                # docker-compose.yml (Qdrant, Postgres, Redis, Ollama, observabilité)
│   ├── k8s/                   # manifestes Kustomize (base + overlays dev/prod)
│   └── helm/                  # chart Helm `rag-system`
│
├── docs/
│   └── adr/                   # Architecture Decision Records (choix Qdrant, Ollama, chunking…)
│
├── scripts/                  # start.sh, stop.sh, k8s-deploy.sh, smoke-test.sh…
└── .github/workflows/        # CI/CD
```

## Installation et usage

### Démarrage rapide avec Docker Compose

Le script `scripts/start.sh` orchestre le démarrage complet : infrastructure (Qdrant, PostgreSQL, Redis), pull des modèles Ollama (`nomic-embed-text` + `llama3.2:3b`), services applicatifs, puis stack d'observabilité.

```bash
bash scripts/start.sh
# ou, si les images sont déjà construites :
bash scripts/start.sh --fast
```

Prérequis : Docker ≥ 24, `docker compose`, et idéalement ≥ 8 Go de RAM disponible (Ollama est gourmand). Le script copie `.env.example` vers `.env` s'il est absent.

Une fois démarré :

| Service | URL |
|---|---|
| Frontend (chat) | http://localhost:3000 |
| RAG API (docs OpenAPI) | http://localhost:8000/docs |
| Ingestion API (docs OpenAPI) | http://localhost:8001/docs |
| Qdrant dashboard | http://localhost:6333/dashboard |
| Grafana | http://localhost:3001 (admin/admin) |
| Jaeger | http://localhost:16686 |
| Prometheus | http://localhost:9090 |

Arrêt : `bash scripts/stop.sh`

### Démarrage manuel (sans Docker Compose)

```bash
# API RAG
cd services/api
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8000

# Service d'ingestion
cd services/ingestion
pip install -r requirements.txt
uvicorn src.main:app --reload --port 8001

# Frontend
cd services/frontend
npm install
npm run dev
```

Cela suppose que Qdrant, PostgreSQL, Redis et Ollama (avec les modèles `nomic-embed-text` et `llama3.2:3b` déjà pullés) tournent par ailleurs et sont accessibles aux URLs par défaut (`localhost:6333`, `localhost:5432`, `localhost:6379`, `localhost:11434`).

### Déploiement Kubernetes

Manifestes Kustomize (`infra/k8s/`, overlays `dev`/`prod`) et chart Helm (`infra/helm/rag-system/`) sont fournis, avec un script `scripts/k8s-deploy.sh` pour le déploiement.
