import React, { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { FileText, ArrowRight, Eye, Download, Plus, Loader2 } from "lucide-react";
import { fetchPapers, PaperListItem, downloadPaperDocx } from "../api/client";
import { useToast } from "../components/Toast";

export const PaperHistory: React.FC = () => {
  const [downloadingId, setDownloadingId] = useState<number | null>(null);
  const { showToast } = useToast();
  const { data: papers = [], isLoading } = useQuery({
    queryKey: ["papers"],
    queryFn: fetchPapers,
  });

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-6">
        <div>
          <h1 className="display text-4xl text-ink font-normal">Generated Papers</h1>
          <p className="text-sm text-muted mt-1">
            History and repository of CBSE Question Papers created with Edkonic RAG.
          </p>
        </div>

        <Link to="/generate" className="btn btn-primary !py-2.5 !px-5 text-sm rounded-full">
          <Plus size={16} /> New Paper
        </Link>
      </div>

      {isLoading ? (
        <div className="text-center py-20 text-muted">Loading papers history...</div>
      ) : papers.length === 0 ? (
        <div className="glass p-12 text-center space-y-4">
          <FileText size={36} className="mx-auto text-muted" />
          <h3 className="text-lg font-semibold text-ink">No question papers generated yet</h3>
          <p className="text-xs text-muted max-w-md mx-auto">
            Get started by configuring syllabus chapters and sections to generate your first examination paper.
          </p>
          <div className="pt-2">
            <Link to="/generate" className="btn btn-primary text-xs">
              Generate Paper Now <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      ) : (
        <div className="glass overflow-hidden border border-line">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th className="py-3.5 px-4 font-medium">#</th>
                  <th className="py-3.5 px-4 font-medium">Title</th>
                  <th className="py-3.5 px-4 font-medium">Marks</th>
                  <th className="py-3.5 px-4 font-medium">Questions</th>
                  <th className="py-3.5 px-4 font-medium">Status</th>
                  <th className="py-3.5 px-4 font-medium">Created</th>
                  <th className="py-3.5 px-4 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {papers.map((p: PaperListItem) => (
                  <tr key={p.id} className="hover:bg-[var(--surface-hover)] transition-colors">
                    <td className="py-3.5 px-4 font-mono text-xs text-muted">#{p.id}</td>
                    <td className="py-3.5 px-4 font-semibold text-ink">
                      <Link to={`/papers/${p.id}`} className="hover:text-blue-500 transition-colors">
                        {p.title}
                      </Link>
                    </td>
                    <td className="py-3.5 px-4 font-mono text-xs text-ink">{p.total_marks}</td>
                    <td className="py-3.5 px-4 text-xs text-muted">{p.question_count}</td>
                    <td className="py-3.5 px-4">
                      {p.status === "ready" && (
                        <span className="chip chip-ok text-xs">Ready</span>
                      )}
                      {p.status === "generating" && (
                        <span className="chip chip-warn text-xs animate-pulse">Generating</span>
                      )}
                      {p.status === "failed" && (
                        <span className="chip chip-bad text-xs">Failed</span>
                      )}
                      {p.status === "queued" && (
                        <span className="chip text-xs">Queued</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-xs text-muted font-mono">
                      {new Date(p.created_at).toLocaleDateString()}
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <Link
                          to={`/papers/${p.id}`}
                          className="btn btn-ghost !p-2 text-xs rounded-full"
                          title="Review questions and approve"
                        >
                          <Eye size={13} /> Review
                        </Link>
                        <Link
                          to={`/papers/${p.id}/preview`}
                          className="btn btn-ghost !p-2 text-xs rounded-full"
                          title="Print-ready preview"
                        >
                          Preview
                        </Link>
                        <button
                          onClick={async () => {
                            try {
                              setDownloadingId(p.id);
                              const filename = await downloadPaperDocx(p.id, "paper");
                              showToast(`Downloaded ${filename}`, "success");
                            } catch (err: any) {
                              showToast(err.message || "Failed to download paper from server", "error");
                            } finally {
                              setDownloadingId(null);
                            }
                          }}
                          disabled={downloadingId === p.id}
                          className="btn btn-ghost !p-2 text-xs rounded-full text-blue-400 cursor-pointer disabled:opacity-50"
                          title="Download DOCX"
                        >
                          {downloadingId === p.id ? (
                            <Loader2 size={13} className="animate-spin" />
                          ) : (
                            <Download size={13} />
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
