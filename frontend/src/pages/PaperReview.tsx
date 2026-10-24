import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ArrowRight, Printer, Sparkles, CheckCircle2, AlertCircle, Database, Layers, ArrowLeft } from "lucide-react";
import {
  fetchPaperDetail,
  updateQuestionStatus,
  updateQuestionContent,
  regenerateQuestion,
  finalizePaper,
} from "../api/client";
import { QuestionCard } from "../components/QuestionCard";
import { CitationDrawer } from "../components/CitationDrawer";

export const PaperReview: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [activeChunkId, setActiveChunkId] = useState<number | null>(null);
  const [finalizeSuccessMessage, setFinalizeSuccessMessage] = useState<string>("");

  const paperId = id ? parseInt(id) : 0;

  // Poll every 2s while generating or queued
  const { data: paper, isLoading } = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => fetchPaperDetail(paperId),
    refetchInterval: (query) => {
      const p = query.state.data;
      if (!p) return 2000;
      return p.status === "ready" || p.status === "failed" ? false : 2000;
    },
  });

  const handleStatusChange = async (questionId: number, status: "accepted" | "rejected" | "draft") => {
    await updateQuestionStatus(paperId, questionId, status);
    queryClient.invalidateQueries({ queryKey: ["paper", paperId] });
  };

  const handleSaveContent = async (questionId: number, content: any) => {
    await updateQuestionContent(paperId, questionId, content);
    queryClient.invalidateQueries({ queryKey: ["paper", paperId] });
  };

  const handleRegenerate = async (questionId: number, instruction?: string) => {
    await regenerateQuestion(paperId, questionId, instruction);
    queryClient.invalidateQueries({ queryKey: ["paper", paperId] });
  };

  const handleAcceptAllPassing = async () => {
    if (!paper) return;
    for (const q of paper.questions) {
      if (q.status !== "accepted") {
        await updateQuestionStatus(paperId, q.id, "accepted");
      }
    }
    queryClient.invalidateQueries({ queryKey: ["paper", paperId] });
  };

  const handleFinalize = async () => {
    if (!paper) return;
    try {
      const res = await finalizePaper(paperId);
      setFinalizeSuccessMessage(res.message || "Saved accepted questions to question bank!");
      queryClient.invalidateQueries({ queryKey: ["paper", paperId] });
      queryClient.invalidateQueries({ queryKey: ["bank"] });
    } catch (err: any) {
      alert("Finalize failed: " + err.message);
    }
  };

  if (isLoading || !paper) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-20 text-center space-y-4">
        <Sparkles size={28} className="animate-spin mx-auto text-blue-500" />
        <h2 className="text-xl font-medium text-ink">Loading Question Paper...</h2>
      </div>
    );
  }

  // Generation In-Progress State
  if (paper.status === "queued" || paper.status === "planning" || paper.status === "generating") {
    return (
      <div className="mx-auto max-w-2xl px-6 py-24 space-y-8 text-center">
        <div className="glass p-8 space-y-6">
          <span className="chip">
            <Sparkles size={14} className="text-blue-500 dark:text-blue-400 animate-pulse" />
            <span>AI Generation Pipeline Active</span>
          </span>

          <h2 className="display text-4xl text-ink font-normal">
            Synthesizing <span className="grad-blue">{paper.title}</span>
          </h2>

          <p className="text-sm text-muted">
            The agent is selecting anchor chunks, running semantic neighbor retrieval, formulating questions against CBSE standards, performing deterministic schema checks, and running LLM moderation.
          </p>

          <div className="space-y-2 pt-4">
            <div className="flex justify-between text-xs text-muted font-mono">
              <span>Stage: {paper.status.toUpperCase()}</span>
              <span>{paper.progress}% Complete</span>
            </div>
            <div className="bar">
              <i style={{ width: `${Math.max(5, paper.progress)}%` }} />
            </div>
          </div>

          <p className="text-xs text-muted italic">
            This typically takes 40–80 seconds on the local embedding pipeline. Please do not close this window.
          </p>
        </div>
      </div>
    );
  }

  // Generation Failed State
  if (paper.status === "failed") {
    return (
      <div className="mx-auto max-w-2xl px-6 py-24 text-center space-y-6">
        <div className="glass p-8 border-rose-500/40 bg-rose-500/10 space-y-4">
          <AlertCircle size={36} className="mx-auto text-rose-500" />
          <h2 className="text-2xl font-bold text-ink">Paper Generation Failed</h2>
          <p className="text-sm text-rose-600 dark:text-rose-300">{paper.error || "An unexpected error occurred during generation."}</p>
          <div className="pt-4 flex justify-center gap-4">
            <Link to="/generate" className="btn btn-primary text-xs">
              Back to Configure
            </Link>
          </div>
        </div>
      </div>
    );
  }

  // Group questions by section and order by configured template sections
  const configuredSectionIds: string[] = (paper.config?.sections || []).map((s: any) => s.id || s.name || s);
  const sectionsMap: Record<string, typeof paper.questions> = {};
  paper.questions.forEach((q) => {
    if (!sectionsMap[q.section]) sectionsMap[q.section] = [];
    sectionsMap[q.section].push(q);
  });
  const sortedSectionEntries = Object.entries(sectionsMap).sort(([secA], [secB]) => {
    const idxA = configuredSectionIds.indexOf(secA);
    const idxB = configuredSectionIds.indexOf(secB);
    if (idxA !== -1 && idxB !== -1) return idxA - idxB;
    return secA.localeCompare(secB);
  });

  const rep = paper.blueprint_report;
  const acceptedCount = paper.questions.filter((q) => q.status === "accepted").length;
  const rejectedCount = paper.questions.filter((q) => q.status === "rejected").length;
  const pendingCount = paper.questions.length - acceptedCount - rejectedCount;

  return (
    <div className="mx-auto max-w-6xl px-6 py-10 space-y-8">
      {/* Top Breadcrumb & Action Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-line pb-6">
        <div>
          <Link to="/papers" className="text-xs text-muted hover:text-ink flex items-center gap-1 mb-2">
            <ArrowLeft size={12} /> Back to Papers
          </Link>
          <h1 className="text-3xl font-bold text-ink tracking-tight">{paper.title}</h1>
          <p className="text-xs text-muted mt-1">
            Generated on {new Date(paper.created_at).toLocaleString()} · {paper.questions.length} Questions · Total Marks:{" "}
            <strong className="text-ink">{rep?.total_marks || 25}</strong>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleAcceptAllPassing}
            className="btn btn-ghost !py-2 !px-4 text-xs rounded-full"
            title="Accept all questions that passed verification"
          >
            <CheckCircle2 size={14} className="text-emerald-400" /> Accept All Passing
          </button>

          <button
            onClick={handleFinalize}
            className="btn btn-ghost !py-2 !px-4 text-xs rounded-full border-blue-500/40 text-blue-300 hover:bg-blue-500/10"
            title="Save accepted questions to question bank"
          >
            <Database size={14} /> Finalize to Bank
          </button>

          <Link
            to={`/papers/${paper.id}/preview`}
            className="btn btn-primary !py-2 !px-4 text-xs rounded-full shadow"
          >
            <Printer size={14} /> Print & Export <ArrowRight size={14} />
          </Link>
        </div>
      </div>

      {finalizeSuccessMessage && (
        <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-300 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} />
            <span>{finalizeSuccessMessage}</span>
          </div>
          <button onClick={() => setFinalizeSuccessMessage("")} className="text-xs opacity-75 hover:opacity-100">
            Dismiss
          </button>
        </div>
      )}

      {/* Blueprint Summary Card */}
      {rep && (
        <div className="glass p-5 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-4 text-center">
          <div className="p-2 border-r border-line">
            <div className="text-xs text-muted">Total Marks</div>
            <div className="text-2xl font-bold text-ink font-mono">{rep.total_marks}</div>
          </div>
          <div className="p-2 border-r border-line">
            <div className="text-xs text-muted">Questions</div>
            <div className="text-2xl font-bold text-ink font-mono">{rep.question_count}</div>
          </div>
          <div className="p-2 border-r border-line">
            <div className="text-xs text-muted">Review Status</div>
            <div className="text-xs font-semibold mt-1">
              <span className="text-emerald-500 dark:text-emerald-400">{acceptedCount} acc</span> ·{" "}
              <span className="text-muted">{pendingCount} dft</span>
              {rejectedCount > 0 && <span className="text-rose-500 dark:text-rose-400"> · {rejectedCount} rej</span>}
            </div>
          </div>
          <div className="p-2 border-r border-line">
            <div className="text-xs text-muted">Competency</div>
            <div className="text-xl font-bold text-sky-500 dark:text-sky-400 font-mono">{rep.competency_percent}%</div>
          </div>
          <div className="p-2 border-r border-line">
            <div className="text-xs text-muted">Flagged Items</div>
            <div className={`text-xl font-bold font-mono ${rep.flagged_count > 0 ? "text-amber-500 dark:text-amber-400" : "text-emerald-500 dark:text-emerald-400"}`}>
              {rep.flagged_count}
            </div>
          </div>
          <div className="p-2">
            <div className="text-xs text-muted">Chapter Marks</div>
            <div className="text-xs text-ink font-mono mt-1">
              {Object.entries(rep.marks_by_chapter).map(([ch, m]) => `Ch${ch}:${m}`).join(" ")}
            </div>
          </div>
        </div>
      )}

      {/* Questions Grouped by Section (ordered by template) */}
      <div className="space-y-10">
        {sortedSectionEntries.map(([sec, qList]) => {
          const marksEach = qList[0]?.marks || 1;
          return (
            <div key={sec} className="space-y-4">
              <div className="flex items-center justify-between border-b border-line pb-2">
                <h2 className="text-xl font-semibold text-ink tracking-tight flex items-center gap-2">
                  <span>Section {sec}</span>
                  <span className="text-xs text-muted font-normal font-sans">
                    ({marksEach} Mark{marksEach > 1 ? "s" : ""} each · {qList.length} Questions)
                  </span>
                </h2>
                <span className="text-xs font-mono text-muted">
                  Subtotal: {qList.reduce((s, q) => s + q.marks, 0)} Marks
                </span>
              </div>

              <div className="space-y-4">
                {qList.map((q) => (
                  <QuestionCard
                    key={q.id}
                    question={q}
                    onStatusChange={(status) => handleStatusChange(q.id, status)}
                    onSaveContent={(content) => handleSaveContent(q.id, content)}
                    onRegenerate={(instruction) => handleRegenerate(q.id, instruction)}
                    onOpenCitation={(cid) => setActiveChunkId(cid)}
                  />
                ))}
              </div>
            </div>
          );
        })}
      </div>

      {/* Textbook Citation Drawer */}
      <CitationDrawer chunkId={activeChunkId} onClose={() => setActiveChunkId(null)} />
    </div>
  );
};
