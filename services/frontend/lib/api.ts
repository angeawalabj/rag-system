/**
 * Fonctions API typées — toutes les requêtes passent par les Route Handlers
 * Next.js (/api/*) pour éviter d'exposer les URLs internes au browser.
 */

import type { Collection, IngestJob, SSEEvent } from "./types";

const API_BASE     = process.env.NEXT_PUBLIC_API_URL     || "http://localhost:8000";
const INGEST_BASE  = process.env.NEXT_PUBLIC_INGEST_URL  || "http://localhost:8001";

// ─── Query RAG (streaming SSE) ────────────────────────────────────────────────

export interface QueryParams {
  question:        string;
  collection:      string;
  top_k?:          number;
  score_threshold?: number;
  use_cache?:      boolean;
}

/**
 * Streame la réponse RAG via SSE.
 * Appelle le Route Handler Next.js /api/query qui proxifie vers le RAG API.
 *
 * @param params    Paramètres de la requête
 * @param onEvent   Callback appelé pour chaque événement SSE parsé
 * @param onError   Callback en cas d'erreur réseau
 */
export async function streamQuery(
  params:  QueryParams,
  onEvent: (event: SSEEvent) => void,
  onError: (err: Error) => void,
): Promise<void> {
  try {
    const res = await fetch("/api/query", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(params),
    });

    if (!res.ok) {
      throw new Error(`HTTP ${res.status} : ${await res.text()}`);
    }
    if (!res.body) {
      throw new Error("Réponse sans body");
    }

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";   // garde la ligne incomplète

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (!data || data === "[DONE]") continue;

        try {
          const event = JSON.parse(data) as SSEEvent;
          onEvent(event);
        } catch {
          // Ligne malformée — ignorée
        }
      }
    }
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

// ─── Collections ──────────────────────────────────────────────────────────────

export async function fetchCollections(): Promise<Collection[]> {
  const res = await fetch(`${API_BASE}/collections`);
  if (!res.ok) throw new Error(`Erreur /collections : ${res.status}`);
  return res.json();
}

// ─── Ingestion ────────────────────────────────────────────────────────────────

export async function uploadDocument(
  file:       File,
  collection: string,
): Promise<{ doc_id: string; job_id: string }> {
  const form = new FormData();
  form.append("file", file);
  form.append("collection", collection);

  const res = await fetch("/api/ingest", { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload échoué : ${res.statusText}`);
  return res.json();
}

export async function pollIngestStatus(docId: string): Promise<IngestJob> {
  const res = await fetch(`${INGEST_BASE}/ingest/${docId}`);
  if (!res.ok) throw new Error(`Statut introuvable : ${res.status}`);
  return res.json();
}
