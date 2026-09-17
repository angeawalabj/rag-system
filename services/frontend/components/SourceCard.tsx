"use client";

import type { Source } from "@/lib/types";

const SOURCE_ICONS: Record<string, string> = {
  pdf:  "📄",
  md:   "📝",
  txt:  "📃",
  url:  "🌐",
  html: "🌐",
};

function ScoreBadge({ score }: { score: number }) {
  const pct   = Math.round(score * 100);
  const color =
    score >= 0.85 ? "text-green-400 border-green-800" :
    score >= 0.75 ? "text-yellow-400 border-yellow-800" :
                    "text-gray-400 border-gray-700";

  return (
    <span className={`text-xs font-mono border rounded px-1.5 py-0.5 ${color}`}>
      {pct}%
    </span>
  );
}

export function SourceCard({ source }: { source: Source }) {
  const icon = SOURCE_ICONS[source.source_type] ?? "📎";
  const name = source.source.length > 40
    ? "…" + source.source.slice(-38)
    : source.source;

  return (
    <div className="flex flex-col gap-1.5 rounded-lg border border-gray-800 bg-gray-900/60 p-3 text-sm">
      {/* En-tête */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="shrink-0">{icon}</span>
          <span className="font-medium text-indigo-300 truncate" title={source.source}>
            [{source.index}] {name}
          </span>
          {source.page && (
            <span className="shrink-0 text-xs text-gray-500">p.{source.page}</span>
          )}
        </div>
        <ScoreBadge score={source.score} />
      </div>

      {/* Aperçu du texte */}
      <p className="text-gray-400 text-xs leading-relaxed line-clamp-3">
        {source.text_preview}
      </p>
    </div>
  );
}
