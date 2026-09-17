// ─── Sources ──────────────────────────────────────────────────────────────────

export interface Source {
  index:        number;
  chunk_id:     string;
  source:       string;
  source_type:  string;
  page:         number | null;
  score:        number;
  text_preview: string;
}

// ─── Messages ─────────────────────────────────────────────────────────────────

export type MessageRole = "user" | "assistant" | "error";

export interface Message {
  id:        string;
  role:      MessageRole;
  content:   string;
  sources:   Source[];
  streaming: boolean;
  cached:    boolean;
  timestamp: Date;
}

// ─── Collections ──────────────────────────────────────────────────────────────

export interface Collection {
  name:         string;
  vector_count: number;
}

// ─── Ingestion ────────────────────────────────────────────────────────────────

export type IngestStatus = "pending" | "processing" | "completed" | "failed";

export interface IngestJob {
  doc_id:      string;
  filename:    string;
  status:      IngestStatus;
  chunk_count: number | null;
  error:       string | null;
}

// ─── SSE Events ───────────────────────────────────────────────────────────────

export interface TokenEvent {
  type:  "token";
  token: string;
  done:  false;
}

export interface SourcesEvent {
  type:    "sources";
  done:    true;
  sources: Source[];
  cached?: boolean;
}

export interface ErrorEvent {
  type:    "error";
  message: string;
  done:    true;
}

export type SSEEvent = TokenEvent | SourcesEvent | ErrorEvent;
