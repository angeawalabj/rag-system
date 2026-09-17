"use client";

import { useCallback, useRef, useState } from "react";
import { pollIngestStatus, uploadDocument } from "@/lib/api";
import type { IngestJob, IngestStatus } from "@/lib/types";

const STATUS_CONFIG: Record<IngestStatus, { label: string; color: string; icon: string }> = {
  pending:    { label: "En attente",  color: "text-gray-400",   icon: "○" },
  processing: { label: "En cours",    color: "text-yellow-400", icon: "◐" },
  completed:  { label: "Terminé",     color: "text-green-400",  icon: "●" },
  failed:     { label: "Échec",       color: "text-red-400",    icon: "✕" },
};

interface UploadPanelProps {
  collection: string;
  onUploaded?: () => void;   // callback pour rafraîchir les collections
}

export function UploadPanel({ collection, onUploaded }: UploadPanelProps) {
  const [jobs, setJobs]           = useState<IngestJob[]>([]);
  const [isDragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList) => {
      for (const file of Array.from(files)) {
        const tempJob: IngestJob = {
          doc_id:      `temp-${Date.now()}-${file.name}`,
          filename:    file.name,
          status:      "pending",
          chunk_count: null,
          error:       null,
        };
        setJobs((prev) => [tempJob, ...prev]);

        try {
          const { doc_id } = await uploadDocument(file, collection);
          updateJob(tempJob.doc_id, { doc_id });
          pollUntilDone(doc_id, tempJob.doc_id);
        } catch (err) {
          updateJob(tempJob.doc_id, {
            status: "failed",
            error: err instanceof Error ? err.message : "Erreur upload",
          });
        }
      }
    },
    [collection],
  );

  function updateJob(tempId: string, patch: Partial<IngestJob>) {
    setJobs((prev) =>
      prev.map((j) => (j.doc_id === tempId ? { ...j, ...patch } : j))
    );
  }

  async function pollUntilDone(realDocId: string, tempId: string) {
    const MAX_POLLS = 60;   // 60 * 3s = 3 min max
    for (let i = 0; i < MAX_POLLS; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      try {
        const status = await pollIngestStatus(realDocId);
        setJobs((prev) =>
          prev.map((j) =>
            j.doc_id === tempId || j.doc_id === realDocId
              ? { ...status, doc_id: realDocId }
              : j
          )
        );
        if (status.status === "completed" || status.status === "failed") {
          if (status.status === "completed") onUploaded?.();
          return;
        }
      } catch {
        // continue le polling malgré une erreur ponctuelle
      }
    }
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
  }

  return (
    <div className="space-y-3">
      {/* Zone de drop */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          isDragging
            ? "border-indigo-500 bg-indigo-950/30"
            : "border-gray-800 hover:border-gray-700 bg-gray-900/40"
        }`}
      >
        <p className="text-sm text-gray-400">
          Glisse un fichier ici ou <span className="text-indigo-400 underline">parcourir</span>
        </p>
        <p className="mt-1 text-xs text-gray-600 font-mono">PDF · Markdown · TXT</p>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.md,.txt"
          className="hidden"
          onChange={(e) => e.target.files && handleFiles(e.target.files)}
        />
      </div>

      {/* Liste des jobs */}
      {jobs.length > 0 && (
        <div className="space-y-1.5">
          {jobs.map((job) => {
            const cfg = STATUS_CONFIG[job.status];
            return (
              <div
                key={job.doc_id}
                className="flex items-center justify-between gap-2 rounded-lg border border-gray-800 bg-gray-900/60 px-3 py-2 text-sm"
              >
                <span className="truncate text-gray-300">{job.filename}</span>
                <div className="flex items-center gap-1.5 shrink-0">
                  {job.chunk_count != null && (
                    <span className="text-xs text-gray-600 font-mono">
                      {job.chunk_count} chunks
                    </span>
                  )}
                  <span className={`text-xs font-mono ${cfg.color}`}>
                    {cfg.icon} {cfg.label}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
