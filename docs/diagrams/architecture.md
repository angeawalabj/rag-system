# Diagrammes d'architecture — RAG System

Tous les diagrammes sont en Mermaid et peuvent être rendus sur GitHub, dans Obsidian, ou via `mmdc`.

---

## 1. Vue C4 — Contexte système

```mermaid
C4Context
    title Contexte système — RAG distribué

    Person(user, "Utilisateur", "Pose des questions\nsur les documents")
    Person(admin, "Administrateur", "Ingère des documents\nvia l'API ou l'UI")

    System(rag, "RAG System", "Pipeline de recherche\naugmentée par LLM.\nRépond aux questions\navec citations de sources.")

    System_Ext(ollama, "Ollama", "LLM et embedding\nlocaux (Llama 3 / Mistral\n+ nomic-embed-text)")

    Rel(user, rag, "Pose une question", "HTTPS / SSE")
    Rel(admin, rag, "Ingère des documents", "HTTPS multipart")
    Rel(rag, ollama, "Embedding + génération", "HTTP REST OpenAI-compat")
```

---

## 2. Vue C4 — Conteneurs (v1 Docker Compose)

```mermaid
C4Container
    title Conteneurs — v1 Docker Compose

    Person(user, "Utilisateur")

    Container(frontend, "Frontend", "Next.js 14", "Chat UI, upload docs,\naffichage des sources")
    Container(api, "RAG API", "FastAPI / Python", "Pipeline retrieve →\naugment → generate")
    Container(ingestion, "Ingestion Service", "Python / RQ Worker", "Chunking, embedding,\nindexation Qdrant")

    ContainerDb(qdrant, "Qdrant", "Vector DB", "Embeddings 768d\n+ payload métadonnées")
    ContainerDb(postgres, "PostgreSQL", "RDBMS", "Métadonnées documents\net statuts d'ingestion")
    ContainerDb(redis, "Redis", "Cache / Queue", "Cache résultats\n+ queue RQ")

    Container(ollama, "Ollama", "LLM Runtime", "nomic-embed-text\n+ llama3.2:3b")
    Container(otel, "OTel Collector", "OpenTelemetry", "Collecte et route\nles traces")
    Container(jaeger, "Jaeger", "Tracing UI", "Visualisation\ndes traces")
    Container(prometheus, "Prometheus", "Métriques", "Scrape /metrics\nde tous les services")
    Container(grafana, "Grafana", "Dashboards", "Métriques + logs")

    Rel(user, frontend, "HTTPS")
    Rel(frontend, api, "REST / SSE")
    Rel(api, qdrant, "gRPC / REST")
    Rel(api, redis, "Cache lookup")
    Rel(api, ollama, "Generate")
    Rel(api, otel, "OTLP traces")
    Rel(api, prometheus, "GET /metrics")
    Rel(ingestion, qdrant, "Upsert vectors")
    Rel(ingestion, postgres, "Update status")
    Rel(ingestion, redis, "RQ jobs")
    Rel(ingestion, ollama, "Embed chunks")
    Rel(otel, jaeger, "OTLP")
    Rel(prometheus, grafana, "PromQL")
```

---

## 3. Flux d'ingestion d'un document

```mermaid
sequenceDiagram
    actor Admin
    participant FE as Frontend
    participant API as RAG API
    participant RQ as Redis Queue
    participant W as Ingestion Worker
    participant Ollama
    participant QD as Qdrant
    participant PG as PostgreSQL

    Admin->>FE: Upload fichier PDF
    FE->>API: POST /ingest (multipart)
    API->>PG: INSERT document (status=pending)
    API->>RQ: enqueue(ingest_job, doc_id)
    API-->>FE: 202 Accepted { job_id, doc_id }

    Note over RQ,W: Traitement asynchrone

    RQ->>W: dépile job
    W->>PG: UPDATE status=processing
    W->>W: Load + clean document
    W->>W: RecursiveCharacterTextSplitter\n(512t, overlap 64t)

    loop Pour chaque chunk
        W->>Ollama: POST /api/embeddings\n{ model: nomic-embed-text, prompt: chunk }
        Ollama-->>W: vector[768]
        W->>QD: upsert point\n{ id, vector, payload }
    end

    W->>PG: UPDATE status=completed,\nchunk_count=N
    W->>RQ: job_done

    FE->>API: GET /ingest/{job_id}/status
    API-->>FE: { status: completed, chunks: N }
```

---

## 4. Flux de requête RAG

```mermaid
sequenceDiagram
    actor User
    participant FE as Frontend
    participant API as RAG API
    participant Redis
    participant Ollama as Ollama (embed)
    participant QD as Qdrant
    participant LLM as Ollama (LLM)

    User->>FE: "Quels sont les résultats Q1 ?"
    FE->>API: POST /query { question, collection?, top_k }

    API->>Redis: GET cache_key(question_hash)
    alt Cache hit
        Redis-->>API: résultat précédent
        API-->>FE: stream réponse (SSE)
    else Cache miss
        API->>Ollama: embed(question)
        Ollama-->>API: query_vector[768]

        API->>QD: search(vector, top_k=5,\nfilter=collection)
        QD-->>API: [chunk1, chunk2, ..., chunk5]\n+ scores + payloads

        API->>API: build_prompt(\n  context=chunks,\n  question=question\n)

        API->>LLM: POST /api/chat (stream)\n{ model, messages }

        loop Streaming tokens
            LLM-->>API: token
            API-->>FE: SSE data: token
        end

        API->>Redis: SET cache_key → résultat (TTL 1h)
    end

    FE->>User: Affiche réponse + sources[chunk1..5]
```

---

## 5. Architecture k8s v2

```mermaid
graph TB
    subgraph "Namespace: rag-system"
        subgraph "Ingress"
            ING[Ingress Controller\nnginx]
        end

        subgraph "Application tier"
            FE[frontend\nDeployment 2x]
            API[rag-api\nDeployment 2x\nHPA 2-8]
            ING_SVC[ingestion-worker\nDeployment 2x]
        end

        subgraph "Data tier — StatefulSets"
            QD[qdrant\nStatefulSet\nPVC 10Gi]
            PG[postgres\nStatefulSet\nPVC 5Gi]
            RD[redis\nStatefulSet\nPVC 1Gi]
        end

        subgraph "LLM tier"
            OL[ollama\nDaemonSet\nPVC 20Gi\nnodeSelector: gpu=true]
        end

        subgraph "Observabilité"
            OC[otel-collector\nDaemonSet]
            JAE[jaeger\nDeployment]
            PROM[prometheus\nStatefulSet\nPVC 20Gi]
            GRAF[grafana\nDeployment\nPVC 2Gi]
        end
    end

    ING --> FE
    ING --> API
    FE --> API
    API --> QD
    API --> RD
    API --> OL
    API --> OC
    ING_SVC --> QD
    ING_SVC --> PG
    ING_SVC --> RD
    ING_SVC --> OL
    OC --> JAE
    PROM --> GRAF
```

---

## 6. Pipeline CI/CD

```mermaid
flowchart LR
    GIT[git push\nmain]
    CI[GitHub Actions\nCI]
    TEST[Tests\nunit + intégration\nOllama mocké]
    BUILD[Docker build\nmulti-stage]
    PUSH[Push GHCR\nghcr.io/user/rag-*]
    DEPLOY_V1[Deploy v1\nRailway]
    DEPLOY_V2[Deploy v2\nkubectl apply\n-k overlays/prod]
    SMOKE[Smoke tests\n/health + /query]
    NOTIFY[Notification\nGitHub Summary]

    GIT --> CI
    CI --> TEST
    TEST --> BUILD
    BUILD --> PUSH
    PUSH --> DEPLOY_V1
    PUSH --> DEPLOY_V2
    DEPLOY_V1 --> SMOKE
    DEPLOY_V2 --> SMOKE
    SMOKE --> NOTIFY
```
