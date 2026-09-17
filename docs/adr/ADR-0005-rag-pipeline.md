# ADR-0005 — Design du pipeline RAG : retrieve → augment → generate

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| Statut      | **Accepté**                         |
| Date        | 2026-06-30                          |
| Décideurs   | équipe projet                       |
| Tags        | rag, api, streaming, cache, prompt  |

## Contexte

Le pipeline RAG doit transformer une question utilisateur en réponse générée par LLM, en s'appuyant sur les chunks indexés dans Qdrant. Trois décisions structurantes à prendre :

1. **Comment scorer et filtrer les chunks retrieval ?**
2. **Comment construire le prompt d'augmentation ?**
3. **Comment streamer la réponse au client ?**

## Décisions

### 1. Retrieve — recherche vectorielle hybride

Recherche par similarité cosine dans Qdrant avec filtrage sur le payload :

```python
results = await qdrant.search(
    collection_name=collection,
    query_vector=query_embedding,
    limit=top_k,            # défaut : 5
    score_threshold=0.70,   # filtre les chunks non pertinents
    query_filter=Filter(    # optionnel : filtrer par collection/date
        must=[FieldCondition(key="collection", match=MatchValue(value=collection))]
    ),
    with_payload=True,      # retourne le texte + métadonnées
)
```

Score threshold à 0.70 : en dessous, le chunk est hors sujet. Au-dessus de 5 chunks, le contexte devient trop long pour le LLM (dégradation de qualité connue).

### 2. Augment — prompt engineering

Template de prompt système strict pour éviter les hallucinations :

```
Tu es un assistant expert. Réponds UNIQUEMENT en te basant sur le contexte fourni.
Si la réponse n'est pas dans le contexte, dis-le explicitement.
Ne fabrique pas d'information. Cite les sources par leur numéro [1], [2]...

Contexte :
[1] {source_1} : {chunk_1}
[2] {source_2} : {chunk_2}
...

Question : {question}
```

### 3. Generate — streaming SSE

Le LLM génère token par token. Le client reçoit les tokens via Server-Sent Events (SSE) pour une UX réactive. Le format SSE est standard HTTP — compatible avec `EventSource` navigateur et `fetch` ReadableStream.

```
data: {"token": "Le", "done": false}
data: {"token": " chiffre", "done": false}
...
data: {"token": ".", "done": false}
data: {"sources": [...], "done": true}
```

### 4. Cache Redis

Les requêtes identiques (même hash SHA256 de question + collection) retournent le résultat en cache avec TTL 1h. Le cache est invalidé si de nouveaux documents sont ingérés dans la même collection.

## Conséquences

- **Positif** : SSE est plus simple que WebSocket pour un flux unidirectionnel serveur → client.
- **Positif** : Le score threshold évite de polluer le contexte avec des chunks non pertinents.
- **Négatif** : Le streaming SSE ne fonctionne pas derrière certains proxies qui bufferisent — ajouter `X-Accel-Buffering: no` en prod.
- **Négatif** : Le cache Redis ne distingue pas les utilisateurs — à adresser si auth multi-tenant en v2.
