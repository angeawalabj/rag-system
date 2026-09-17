# ADR-0001 — Choix du vector store : Qdrant

| Champ       | Valeur                          |
|-------------|---------------------------------|
| Statut      | **Accepté**                     |
| Date        | 2026-06-29                      |
| Décideurs   | équipe projet                   |
| Tags        | storage, vector, infra          |

## Contexte

Le système RAG nécessite un moteur de recherche vectorielle capable de :
- Stocker des embeddings 768 dimensions (nomic-embed-text)
- Filtrer par métadonnées (source, date, collection)
- Servir des requêtes de similarité en < 50 ms p99
- Fonctionner en Docker Compose (v1) et Kubernetes (v2)
- Exposer une API REST standard sans SDK obligatoire

## Options évaluées

| Critère              | Qdrant        | Chroma        | Weaviate      | pgvector      |
|----------------------|---------------|---------------|---------------|---------------|
| Image Docker officielle | ✅          | ✅            | ✅            | ✅            |
| API REST native      | ✅            | ⚠️ Python SDK | ✅            | ❌ SQL only   |
| Filtres sur payload  | ✅ rich       | ⚠️ basique    | ✅            | ✅            |
| Helm chart officiel  | ✅            | ❌            | ✅            | ❌            |
| Persistance volume   | ✅            | ✅            | ✅            | ✅ (Postgres) |
| Snapshots / backup   | ✅ natif      | ❌            | ✅            | ⚠️ pg_dump   |
| Latence p99 (1M vec) | ~8 ms         | ~40 ms        | ~12 ms        | ~25 ms        |
| Maturité v2 k8s      | ✅ chart stable | ❌           | ✅            | N/A           |

## Décision

**Qdrant** est retenu comme vector store principal.

Raisons déterminantes :
1. Le Helm chart officiel `qdrant/qdrant` supporte nativement le StatefulSet + PVC — indispensable pour la v2 k8s.
2. L'API REST + gRPC permet de changer de SDK client sans modifier le contrat.
3. Les filtres `must` / `should` / `must_not` sur le payload JSON couvrent les cas d'usage de filtrage par collection et par date sans index secondaire.
4. La persistance sur volume nommé Docker est triviale et cohérente avec le mapping PVC k8s.

## Conséquences

- **Positif** : API stable, upgrade de version sans migration de schéma.
- **Positif** : Les snapshots Qdrant permettent un backup sans arrêt du service.
- **Négatif** : Dépendance à un vendor spécifique — migration vers pgvector possible si la simplicité opérationnelle prime en v3.
- **Négatif** : Qdrant ne fait pas de full-text search natif — PostgreSQL reste nécessaire pour les métadonnées textuelles.

## Révision prévue

À réévaluer si pgvector 0.7+ atteint des latences comparables avec les index HNSW natifs PostgreSQL.
