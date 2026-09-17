"use client";

import { useState, type KeyboardEvent } from "react";
import type { Collection } from "@/lib/types";

interface QueryInputProps {
  onSubmit:    (question: string) => void;
  disabled:    boolean;
  collections: Collection[];
  selected:    string;
  onSelectCollection: (name: string) => void;
}

export function QueryInput({
  onSubmit,
  disabled,
  collections,
  selected,
  onSelectCollection,
}: QueryInputProps) {
  const [value, setValue] = useState("");

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }

  return (
    <div className="border-t border-gray-800 bg-gray-950/95 backdrop-blur p-4">
      <div className="mx-auto max-w-3xl">
        {/* Sélecteur de collection */}
        <div className="mb-2 flex items-center gap-2">
          <span className="text-xs text-gray-500 font-mono">collection:</span>
          <select
            value={selected}
            onChange={(e) => onSelectCollection(e.target.value)}
            className="text-xs bg-gray-900 border border-gray-800 rounded px-2 py-1 text-gray-300 font-mono focus:outline-none focus:border-indigo-700"
          >
            {collections.length === 0 && (
              <option value="documents">documents</option>
            )}
            {collections.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.vector_count} vecteurs)
              </option>
            ))}
          </select>
        </div>

        {/* Zone de saisie */}
        <div className="flex items-end gap-2 rounded-xl border border-gray-800 bg-gray-900 p-2 focus-within:border-indigo-700 transition-colors">
          <textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Pose une question sur tes documents…"
            rows={1}
            className="flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-gray-100 placeholder-gray-600 focus:outline-none disabled:opacity-50 max-h-32"
            style={{ minHeight: "2.25rem" }}
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="shrink-0 rounded-lg bg-indigo-600 px-3.5 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:bg-gray-800 disabled:text-gray-600 disabled:cursor-not-allowed"
          >
            {disabled ? "…" : "Envoyer"}
          </button>
        </div>

        <p className="mt-1.5 text-xs text-gray-600">
          Entrée pour envoyer · Maj+Entrée pour une nouvelle ligne
        </p>
      </div>
    </div>
  );
}
