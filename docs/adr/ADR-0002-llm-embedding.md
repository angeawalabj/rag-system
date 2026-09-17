# ADR-0002 — LLM et modèle d'embedding : Ollama local

| Champ       | Valeur                          |
|-------------|---------------------------------|
| Statut      | **Accepté**                     |
| Date        | 2026-06-29                      |
| Décideurs   | équipe projet                   |
| Tags        | llm, embedding, infra, coût     |

## Contexte

Le pipeline RAG nécessite deux modèles :
1. Un **modèle d'embedding** pour vectoriser les chunks à l'ingestion et les requêtes
2. Un **LLM de génération** pour produire la réponse augmentée

Contraintes identifiées :
- Coût d'inférence = 0 € (critère absolu pour la démo)
- Fonctionne offline (pas de dépendance réseau en dev)
- API compatible avec les clients Python standard
- Doit tourner sur une machine de développement standard (8 GB RAM minimum)

## Options évaluées

### Embedding

| Modèle               | Dimensions | RAM   | Qualité MTEB | Via Ollama |
|----------------------|------------|-------|--------------|------------|
| nomic-embed-text     | 768        | ~1 GB | 62.4 (BEIR)  | ✅         |
| mxbai-embed-large    | 1024       | ~1.5 GB | 64.7       | ✅         |
| all-minilm           | 384        | ~90 MB | 56.3        | ✅         |
| text-embedding-3-small | 1536     | N/A   | 62.3         | ❌ OpenAI  |

### LLM

| Modèle          | RAM    | Context | Qualité | Via Ollama |
|-----------------|--------|---------|---------|------------|
| llama3.2:3b     | ~2 GB  | 128k    | ⭐⭐⭐  | ✅         |
| llama3.2:1b     | ~1 GB  | 128k    | ⭐⭐    | ✅         |
| mistral:7b      | ~5 GB  | 32k     | ⭐⭐⭐⭐ | ✅         |
| phi3:mini       | ~2 GB  | 128k    | ⭐⭐⭐  | ✅         |
| gemma2:2b       | ~2 GB  | 8k      | ⭐⭐⭐  | ✅         |

## Décision

- **Embedding** : `nomic-embed-text` — meilleur ratio qualité/RAM, 768 dimensions standard pour Qdrant.
- **LLM** : `llama3.2:3b` par défaut, `mistral:7b` si la machine a ≥ 8 GB RAM libre.
- **Runtime** : Ollama comme serveur unique exposant les deux modèles sur `:11434`.

L'API Ollama est compatible OpenAI (`/v1/embeddings`, `/v1/chat/completions`) — migration vers un provider cloud sans changer le code client.

## Architecture résultante

```
┌─────────────────────────────────┐
│  Ollama (:11434)                │
│  ├── nomic-embed-text  (embed)  │
│  └── llama3.2:3b       (chat)   │
└─────────────────────────────────┘
         ↑ API OpenAI-compatible
  ingestion-service  │  rag-api
```

## Conséquences

- **Positif** : Zéro coût, zéro latence réseau, données restent locales.
- **Positif** : `OLLAMA_BASE_URL` suffit à basculer vers un provider distant.
- **Négatif** : Ollama nécessite ~3–7 GB RAM selon le modèle — Docker Compose doit allouer `mem_limit`.
- **Négatif** : Pas de GPU par défaut en CI — les tests d'intégration mockent l'API Ollama.
- **Négatif** : En v2 k8s, Ollama tourne en DaemonSet sur les nodes avec GPU ou en sidecar — à adresser dans ADR-0005.

## Configuration requise (docker-compose)

```yaml
ollama:
  image: ollama/ollama:latest
  mem_limit: 8g        # mistral:7b
  # ou mem_limit: 4g  # llama3.2:3b
  volumes:
    - ollama_data:/root/.ollama
```

## Révision prévue

Si les coûts d'inférence cloud deviennent acceptables ou si une API commune (OpenRouter) simplifie la gestion des modèles, migrer vers un provider distant en changeant uniquement `OLLAMA_BASE_URL`.
