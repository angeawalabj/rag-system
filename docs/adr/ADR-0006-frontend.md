# ADR-0006 — Architecture Frontend : Next.js App Router + SSE

| Champ       | Valeur                              |
|-------------|-------------------------------------|
| Statut      | **Accepté**                         |
| Date        | 2026-06-30                          |
| Décideurs   | équipe projet                       |
| Tags        | frontend, next.js, sse, ux          |

## Contexte

Le frontend doit offrir deux fonctionnalités principales :
1. **Chat** : envoyer une question, afficher la réponse streamée token par token avec les sources citées
2. **Ingestion** : uploader des documents et suivre leur statut en temps réel

Contrainte : pas de framework CSS lourd — le bundle doit rester < 200 KB gzippé.

## Décisions

### Stack retenue

| Couche | Choix | Raison |
|--------|-------|--------|
| Framework | Next.js 14 App Router | Server Components, streaming natif, `use client` granulaire |
| Styling | Tailwind CSS | Pas de runtime CSS, classes utilitaires, bundle minimal |
| State | `useState` + `useReducer` | Pas de Redux — l'état du chat est local et simple |
| SSE client | `fetch` + `ReadableStream` | Pas de lib externe, contrôle total sur le parsing |
| Upload | `FormData` natif | Multipart sans dépendance |
| Types | TypeScript strict | `strict: true`, pas de `any` |

### Gestion du streaming SSE côté client

```typescript
// Pas d'EventSource — fetch donne plus de contrôle
const res = await fetch('/api/query', { method: 'POST', body: ... });
const reader = res.body!.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const lines = decoder.decode(value).split('\n');
  for (const line of lines) {
    if (!line.startsWith('data: ')) continue;
    const event = JSON.parse(line.slice(6));
    if (event.done) setSources(event.sources);
    else setAnswer(prev => prev + event.token);
  }
}
```

### Structure de composants

```
frontend/
├── app/
│   ├── layout.tsx          ← layout racine, providers
│   ├── page.tsx            ← redirect → /chat
│   ├── chat/
│   │   └── page.tsx        ← page principale du chat
│   └── api/
│       ├── query/route.ts  ← proxy SSE vers RAG API (évite CORS)
│       └── ingest/route.ts ← proxy upload vers Ingestion Service
├── components/
│   ├── ChatWindow.tsx      ← historique des messages
│   ├── MessageBubble.tsx   ← bulle message + sources
│   ├── QueryInput.tsx      ← input + bouton submit
│   ├── SourceCard.tsx      ← carte de source citée
│   ├── UploadPanel.tsx     ← drag & drop + progress
│   └── StatusBadge.tsx     ← badge statut ingestion
└── lib/
    ├── api.ts              ← fonctions fetch typées
    └── types.ts            ← types partagés
```

## Conséquences

- **Positif** : Les Route Handlers Next.js (`app/api/`) proxifient les appels vers les microservices — le browser ne connaît pas les URLs internes.
- **Positif** : Server Components pour le layout — zéro JS envoyé pour les parties statiques.
- **Négatif** : Le streaming SSE à travers un Route Handler Next.js nécessite `TransformStream` — plus verbeux qu'un proxy direct mais plus sécurisé.
