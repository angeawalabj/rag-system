# ADR-0007 — Stratégie d'observabilité : dashboards, alertes, SLO

| Champ       | Valeur                              |
|-------------|--------------------------------------|
| Statut      | **Accepté**                          |
| Date        | 2026-06-30                           |
| Décideurs   | équipe projet                        |
| Tags        | observabilité, grafana, prometheus, slo |

## Contexte

Les métriques Prometheus existent depuis la semaine 1-2 (`rag_ingestion_*`, `rag_queries_*`, `rag_chunks_*`) mais ne sont pas encore visualisées ni alertées. Cet ADR fixe :
1. Les SLO (Service Level Objectives) du système
2. La structure des dashboards Grafana
3. Les règles d'alerte Prometheus

## SLO retenus

| Indicateur                          | Cible          | Justification |
|--------------------------------------|----------------|----------------|
| Latence requête RAG (p95)            | < 8s           | LLM local CPU ~3-5s génération + 1-2s retrieve |
| Latence requête RAG (p99, cache hit) | < 200ms        | Cache Redis doit être quasi-instantané |
| Taux d'erreur requêtes               | < 2%           | Tolère les questions hors-scope (pas de chunk trouvé) |
| Durée d'ingestion (p95, < 5MB)       | < 60s          | Embedding séquentiel par batch de 16 |
| Disponibilité Qdrant                 | 99.5%          | Single instance v1 — pas de HA avant v2 |
| Cache hit rate                       | > 30%          | Questions répétées en démo/dev |

## Dashboards Grafana

### 1. `rag-overview` — Vue d'ensemble système
- Requêtes/min (rate)
- Latence p50/p95/p99 (time series)
- Taux de cache hit (gauge)
- Erreurs/min par type

### 2. `rag-ingestion` — Pipeline d'ingestion
- Documents traités (counter, par statut)
- Chunks créés/min
- Durée d'embedding (histogram heatmap)
- Queue RQ : jobs en attente

### 3. `rag-infra` — Infrastructure
- Qdrant : vecteurs totaux, latence recherche
- PostgreSQL : connexions actives, requêtes/s
- Redis : mémoire utilisée, hit rate cache
- Ollama : requêtes/min, latence par modèle

## Règles d'alerte Prometheus

| Alerte                        | Condition                                  | Sévérité |
|--------------------------------|---------------------------------------------|----------|
| `RAGHighLatency`               | p95 query_duration > 10s pendant 5 min      | warning  |
| `RAGHighErrorRate`             | taux d'erreur > 5% pendant 5 min            | critical |
| `IngestionQueueBacklog`        | jobs RQ en attente > 50 pendant 10 min      | warning  |
| `IngestionFailureSpike`        | > 3 échecs d'ingestion en 5 min             | warning  |
| `QdrantDown`                   | scrape Qdrant échoue depuis 1 min           | critical |
| `OllamaDown`                   | scrape Ollama échoue depuis 1 min           | critical |
| `CacheHitRateLow`              | hit rate < 10% pendant 30 min               | info     |

## Conséquences

- **Positif** : Les SLO donnent un langage commun pour juger si le système "va bien".
- **Positif** : Les dashboards sont provisionnés automatiquement (`grafana/provisioning/dashboards/`) — zéro configuration manuelle au démarrage.
- **Négatif** : Pas d'Alertmanager en v1 (alertes visibles dans Prometheus UI uniquement) — à ajouter en v2 avec notification Slack/email.
- **Révision** : Réévaluer les seuils SLO après 2 semaines d'usage réel — les valeurs actuelles sont des estimations basées sur du CPU inference.
