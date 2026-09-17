"use client";

import type { Message } from "@/lib/types";
import { SourceCard } from "./SourceCard";

function Timestamp({ date }: { date: Date }) {
  return (
    <span className="text-xs text-gray-600">
      {date.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })}
    </span>
  );
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser      = message.role === "user";
  const isError     = message.role === "error";
  const isStreaming = message.streaming;

  if (isUser) {
    return (
      <div className="flex justify-end gap-2 mb-4">
        <div className="max-w-[75%]">
          <div className="rounded-2xl rounded-tr-sm bg-indigo-600 px-4 py-2.5 text-sm text-white">
            {message.content}
          </div>
          <div className="mt-1 flex justify-end">
            <Timestamp date={message.timestamp} />
          </div>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex gap-3 mb-4">
        <div className="shrink-0 w-7 h-7 rounded-full bg-red-900 flex items-center justify-center text-sm">
          ⚠
        </div>
        <div className="max-w-[80%] rounded-2xl rounded-tl-sm border border-red-800 bg-red-950/50 px-4 py-2.5 text-sm text-red-300">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="flex gap-3 mb-6">
      {/* Avatar */}
      <div className="shrink-0 w-7 h-7 rounded-full bg-green-900/60 border border-green-800 flex items-center justify-center text-xs font-bold text-green-400">
        R
      </div>

      <div className="flex-1 min-w-0">
        {/* Bulle réponse */}
        <div className="rounded-2xl rounded-tl-sm border border-gray-800 bg-gray-900/80 px-4 py-3">
          <p className={`text-sm text-gray-100 leading-relaxed whitespace-pre-wrap ${isStreaming ? "cursor-blink" : ""}`}>
            {message.content || (
              <span className="text-gray-500 italic">Génération en cours…</span>
            )}
          </p>
        </div>

        {/* Meta : timestamp + badge cached */}
        <div className="mt-1 flex items-center gap-2">
          <Timestamp date={message.timestamp} />
          {message.cached && (
            <span className="text-xs text-gray-600 font-mono">[cache]</span>
          )}
        </div>

        {/* Sources */}
        {!isStreaming && message.sources.length > 0 && (
          <div className="mt-3">
            <p className="text-xs text-gray-500 font-mono mb-2 uppercase tracking-wider">
              Sources ({message.sources.length})
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {message.sources.map((s) => (
                <SourceCard key={s.chunk_id} source={s} />
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
