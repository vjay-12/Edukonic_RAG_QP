import React from "react";
import { X, BookOpen, Layers, Bookmark } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchChunkCitation } from "../api/client";

interface CitationDrawerProps {
  chunkId: number | null;
  onClose: () => void;
}

export const CitationDrawer: React.FC<CitationDrawerProps> = ({ chunkId, onClose }) => {
  const { data: chunk, isLoading } = useQuery({
    queryKey: ["chunk", chunkId],
    queryFn: () => (chunkId ? fetchChunkCitation(chunkId) : null),
    enabled: !!chunkId,
  });

  if (!chunkId) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs transition-opacity animate-in fade-in duration-200">
      <div className="fixed inset-0" onClick={onClose} />

      <aside className="relative z-10 w-full max-w-xl h-full bg-[var(--bg-elev)] border-l border-line p-6 flex flex-col shadow-2xl overflow-y-auto">
        <div className="flex items-center justify-between pb-4 border-b border-line">
          <div className="flex items-center gap-2 text-sm text-[var(--ok)] font-medium">
            <BookOpen size={16} />
            <span>Verified Textbook Evidence</span>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full hover:bg-[var(--surface-hover)] text-muted hover:text-ink transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {isLoading ? (
          <div className="py-20 text-center text-muted">Loading citation text...</div>
        ) : chunk ? (
          <div className="mt-6 flex flex-col gap-5">
            <div>
              <div className="flex items-center gap-2 mb-2">
                <span className="chip text-xs">Chapter {chunk.chapter_no}</span>
                <span className="chip text-xs">Pages {chunk.page_start}–{chunk.page_end}</span>
                <span className="chip text-xs uppercase">{chunk.content_type}</span>
                <span className="chip text-xs">{chunk.token_count} tokens</span>
              </div>
              <h3 className="text-xl font-semibold text-ink tracking-tight">
                {chunk.section_heading || "Textbook Section"}
              </h3>
              <p className="text-xs text-muted mt-1 font-mono">{chunk.citation}</p>
            </div>

            <div className="rounded-xl border border-line bg-[var(--surface)] p-5 text-sm leading-relaxed text-ink whitespace-pre-wrap font-sans">
              {chunk.text}
            </div>

            <div className="p-4 rounded-xl border border-[var(--border)] bg-blue-500/5 text-xs text-blue-600 dark:text-blue-300 flex items-start gap-3">
              <Bookmark size={18} className="shrink-0 mt-0.5 text-blue-500" />
              <span>
                This excerpt was retrieved directly from the official NCERT Class 10 textbook using local pgvector embeddings (HNSW cosine search).
              </span>
            </div>
          </div>
        ) : (
          <div className="py-20 text-center text-muted">Citation details not found.</div>
        )}
      </aside>
    </div>
  );
};
