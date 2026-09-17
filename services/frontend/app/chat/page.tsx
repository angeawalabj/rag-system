"use client";

import { useEffect, useState } from "react";
import { ChatWindow } from "@/components/ChatWindow";
import { QueryInput } from "@/components/QueryInput";
import { UploadPanel } from "@/components/UploadPanel";
import { fetchCollections, streamQuery } from "@/lib/api";
import type { Collection, Message, SSEEvent } from "@/lib/types";

function newId(): string {
  return crypto.randomUUID();
}

export default function ChatPage() {
  const [messages, setMessages]       = useState<Message[]>([]);
  const [isStreaming, setStreaming]   = useState(false);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [collection, setCollection]   = useState("documents");
  const [showUpload, setShowUpload]   = useState(false);

  useEffect(() => {
    refreshCollections();
  }, []);

  async function refreshCollections() {
    try {
      const cols = await fetchCollections();
      setCollections(cols);
    } catch {
      // Le RAG API n'est peut-être pas encore prêt — pas bloquant
    }
  }

  function handleSubmit(question: string) {
    const userMsg: Message = {
      id: newId(),
      role: "user",
      content: question,
      sources: [],
      streaming: false,
      cached: false,
      timestamp: new Date(),
    };

    const assistantId = newId();
    const assistantMsg: Message = {
      id: assistantId,
      role: "assistant",
      content: "",
      sources: [],
      streaming: true,
      cached: false,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setStreaming(true);

    streamQuery(
      { question, collection, top_k: 5, use_cache: true },
      (event: SSEEvent) => {
        if (event.type === "token") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, content: m.content + event.token }
                : m
            )
          );
        } else if (event.type === "sources") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    sources: event.sources,
                    streaming: false,
                    cached: event.cached ?? false,
                  }
                : m
            )
          );
          setStreaming(false);
        } else if (event.type === "error") {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? { ...m, role: "error", content: event.message, streaming: false }
                : m
            )
          );
          setStreaming(false);
        }
      },
      (err: Error) => {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  role: "error",
                  content: `Erreur de connexion : ${err.message}`,
                  streaming: false,
                }
              : m
          )
        );
        setStreaming(false);
      },
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-950/95 backdrop-blur px-4 py-3">
        <div className="mx-auto flex max-w-3xl items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-green-400">●</span>
            <h1 className="text-sm font-semibold text-gray-100">RAG System</h1>
            <span className="text-xs text-gray-600 font-mono">v1</span>
          </div>
          <button
            onClick={() => setShowUpload((v) => !v)}
            className="rounded-lg border border-gray-800 px-3 py-1.5 text-xs text-gray-300 hover:border-gray-700 hover:bg-gray-900 transition-colors"
          >
            {showUpload ? "Fermer" : "📎 Ajouter des documents"}
          </button>
        </div>
      </header>

      {/* Panneau d'upload (toggle) */}
      {showUpload && (
        <div className="border-b border-gray-800 bg-gray-900/40 px-4 py-4">
          <div className="mx-auto max-w-3xl">
            <UploadPanel collection={collection} onUploaded={refreshCollections} />
          </div>
        </div>
      )}

      {/* Fenêtre de chat */}
      <ChatWindow messages={messages} />

      {/* Input */}
      <QueryInput
        onSubmit={handleSubmit}
        disabled={isStreaming}
        collections={collections}
        selected={collection}
        onSelectCollection={setCollection}
      />
    </div>
  );
}
