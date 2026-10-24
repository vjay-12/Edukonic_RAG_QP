import React, { useState } from "react";
import { Check, X, RotateCw, Edit3, ChevronDown, ChevronUp, BookOpen, AlertCircle, CheckCircle2, AlertTriangle, Save } from "lucide-react";
import { QuestionData } from "../api/client";
import { formatChemicalFormulas, stripOptionPrefix, stripSubQuestionPrefix, getRomanNumeral, formatMarks, cleanStemForSubquestions } from "../utils/formatters";

interface QuestionCardProps {
  question: QuestionData;
  onStatusChange: (status: "accepted" | "rejected" | "draft") => void;
  onSaveContent: (newContent: any) => void;
  onRegenerate: (instruction?: string) => Promise<void>;
  onOpenCitation: (chunkId: number) => void;
}

export const QuestionCard: React.FC<QuestionCardProps> = ({
  question,
  onStatusChange,
  onSaveContent,
  onRegenerate,
  onOpenCitation,
}) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [showRegenModal, setShowRegenModal] = useState(false);
  const [regenInstruction, setRegenInstruction] = useState("");
  const [isRegenerating, setIsRegenerating] = useState(false);

  // Edit form state
  const [editStem, setEditStem] = useState(question.content?.stem || "");
  const [editAnswer, setEditAnswer] = useState(question.content?.answer || "");

  const c = question.content || {};
  const val = question.validation || { verdict: "pass", issues: [] };
  const source = c.source || { chunk_ids: [], pages: [] };
  const pages: number[] = source.pages || [];
  const chunkIds: number[] = source.chunk_ids || question.source_chunk_ids || [];
  const primaryChunkId = chunkIds.length > 0 ? chunkIds[0] : null;

  const pageStr = pages.length > 0 ? `p.${Math.min(...pages)}–${Math.max(...pages)}` : "NCERT";

  const handleSave = () => {
    const updated = {
      ...question.content,
      stem: editStem,
      answer: editAnswer,
    };
    onSaveContent(updated);
    setIsEditing(false);
  };

  const handleRegenSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsRegenerating(true);
    try {
      await onRegenerate(regenInstruction);
      setShowRegenModal(false);
      setRegenInstruction("");
    } finally {
      setIsRegenerating(false);
    }
  };

  return (
    <div
      className={`glass p-6 transition-all border ${
        question.status === "accepted"
          ? "border-emerald-500/40 bg-emerald-950/10"
          : question.status === "rejected"
          ? "border-rose-500/40 bg-rose-950/10 opacity-70"
          : "border-line"
      }`}
    >
      {/* Top Header & Badges */}
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-lg text-ink">Q{question.slot_no}.</span>
          <span className="chip text-xs">Section {question.section}</span>
          <span className="chip text-xs">Ch {question.chapter_no}</span>
          <span className="chip text-xs uppercase font-mono">{question.type}</span>
          <span className="chip text-xs font-semibold">{formatMarks(question.marks)}</span>
          <span className="chip text-xs capitalize">{question.difficulty}</span>
          {question.competency && (
            <span className="chip text-xs text-sky-500 dark:text-sky-400 border-sky-500/30 bg-sky-500/10">Competency</span>
          )}

          {/* Validation Verdict Chip */}
          {val.verdict === "pass" && (
            <span className="chip chip-ok text-xs" title="Passed automated RAG validation">
              <CheckCircle2 size={12} /> Validated
            </span>
          )}
          {val.verdict === "warn" && (
            <span className="chip chip-warn text-xs" title={val.issues?.join("; ") || "Minor warning"}>
              <AlertTriangle size={12} /> Needs Review
            </span>
          )}
          {val.verdict === "fail" && (
            <span className="chip chip-bad text-xs" title={val.issues?.join("; ") || "Defect flagged"}>
              <AlertCircle size={12} /> Flagged
            </span>
          )}
        </div>

        {/* Source Citation Pill */}
        {primaryChunkId ? (
          <button
            onClick={() => onOpenCitation(primaryChunkId)}
            className="chip hover:bg-[var(--surface-hover)] hover:text-ink transition-colors cursor-pointer text-xs"
            title="Inspect source textbook text in citation drawer"
          >
            <BookOpen size={12} className="text-blue-500 dark:text-blue-400" />
            <span>NCERT Science 10 · {pageStr}</span>
          </button>
        ) : (
          <span className="chip text-xs text-muted">NCERT Science 10</span>
        )}
      </div>

      {/* Validation issues warning banner if present */}
      {val.issues && val.issues.length > 0 && (
        <div className="mb-4 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300 flex items-start gap-2">
          <AlertTriangle size={15} className="shrink-0 mt-0.5 text-amber-500" />
          <div>
            <strong>Moderator Notes:</strong> {val.issues.join(" ")}
          </div>
        </div>
      )}

      {/* Stem Content */}
      {isEditing ? (
        <div className="space-y-3 mb-4">
          <label className="text-xs text-muted font-medium block">Question Stem:</label>
          <textarea
            className="field w-full text-sm font-sans"
            rows={3}
            value={editStem}
            onChange={(e) => setEditStem(e.target.value)}
          />
        </div>
      ) : (
        <p className="text-base font-medium text-ink leading-relaxed mb-4 whitespace-pre-wrap">
          {(c.sub_questions && c.sub_questions.length > 0)
            ? cleanStemForSubquestions(c.stem, c.sub_questions)
            : formatChemicalFormulas(c.stem)}
        </p>
      )}

      {/* MCQ Options */}
      {c.options && Array.isArray(c.options) && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mb-4">
          {c.options.map((opt: string, i: number) => {
            const letter = String.fromCharCode(65 + i);
            const isCorrect = c.correct_option === letter;
            const cleanOpt = stripOptionPrefix(opt);
            const formattedOpt = formatChemicalFormulas(cleanOpt);
            return (
              <div
                key={i}
                className={`p-3 rounded-xl border text-sm flex items-start gap-2.5 transition-colors ${
                  isCorrect
                    ? "border-emerald-500/50 bg-emerald-500/10 text-emerald-700 dark:text-emerald-200"
                    : "border-line bg-[var(--surface)] text-ink"
                }`}
              >
                <span className={`font-bold font-mono text-xs px-1.5 py-0.5 rounded ${isCorrect ? "bg-emerald-500/20 text-emerald-600 dark:text-emerald-300" : "bg-black/5 dark:bg-white/10 text-muted"}`}>
                  ({letter})
                </span>
                <span>{formattedOpt}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Sub-Questions (Render consistently for all question types) */}
      {c.sub_questions && Array.isArray(c.sub_questions) && (
        <div className="space-y-2 mb-4 bg-[var(--surface)] p-4 rounded-xl border border-line">
          <h4 className="text-xs uppercase tracking-wider text-muted font-semibold mb-2">Sub-Questions:</h4>
          {c.sub_questions.map((sq: any, i: number) => {
            const roman = getRomanNumeral(i);
            const cleanSubStem = stripSubQuestionPrefix(sq.stem);
            const formattedSubStem = formatChemicalFormulas(cleanSubStem);
            return (
              <div key={i} className="text-sm text-ink flex items-start gap-2">
                <span className="font-semibold text-xs px-1.5 py-0.5 rounded bg-black/5 dark:bg-white/10 text-muted shrink-0 mt-0.5 font-mono">{roman}</span>
                <div className="grow">
                  <span>{formattedSubStem}</span>
                  <span className="ml-2 font-mono text-xs text-muted">[{formatMarks(sq.marks)}]</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Collapsible Answer & Marking Scheme */}
      <div className="border-t border-line pt-3 mt-3">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1.5 text-xs font-medium text-muted hover:text-ink transition-colors cursor-pointer"
        >
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          <span>{isExpanded ? "Hide" : "View"} Model Answer & Marking Scheme</span>
        </button>

        {isExpanded && (
          <div className="mt-3 p-4 rounded-xl bg-[var(--surface)] border border-line space-y-3 text-sm animate-in fade-in duration-150">
            {isEditing ? (
              <div className="space-y-2">
                <label className="text-xs text-muted font-medium block">Model Answer:</label>
                <textarea
                  className="field w-full text-sm font-sans"
                  rows={3}
                  value={editAnswer}
                  onChange={(e) => setEditAnswer(e.target.value)}
                />
              </div>
            ) : (
              <div>
                <strong className="text-xs uppercase text-muted block mb-1">Model Answer:</strong>
                {c.correct_option && (
                  <span className="font-bold text-emerald-600 dark:text-emerald-400 mr-2">Correct Option ({c.correct_option}) —</span>
                )}
                <span className="text-ink leading-relaxed">{c.answer}</span>
              </div>
            )}

            {c.marking_scheme && Array.isArray(c.marking_scheme) && c.marking_scheme.length > 0 && (
              <div>
                <strong className="text-xs uppercase text-muted block mb-1.5">Step-Wise Marking Scheme:</strong>
                <ul className="space-y-1 list-disc list-inside text-xs text-muted">
                  {c.marking_scheme.map((step: any, idx: number) => (
                    <li key={idx}>
                      <span className="text-ink">{step.step}</span>
                      <span className="font-mono text-muted ml-2">[{formatMarks(step.marks)}]</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action Footer */}
      <div className="flex flex-wrap items-center justify-between gap-3 mt-4 pt-3 border-t border-line">
        <div className="flex items-center gap-2">
          {question.status !== "accepted" ? (
            <button
              onClick={() => onStatusChange("accepted")}
              className="btn btn-ghost !py-1.5 !px-3 text-xs hover:border-emerald-500 hover:text-emerald-500 rounded-full"
            >
              <Check size={14} /> Accept
            </button>
          ) : (
            <span className="chip chip-ok text-xs font-medium">
              <Check size={12} /> Accepted
            </span>
          )}

          {question.status !== "rejected" ? (
            <button
              onClick={() => onStatusChange("rejected")}
              className="btn btn-ghost !py-1.5 !px-3 text-xs hover:border-rose-500 hover:text-rose-500 rounded-full"
            >
              <X size={14} /> Reject
            </button>
          ) : (
            <span className="chip chip-bad text-xs font-medium">
              <X size={12} /> Rejected
            </span>
          )}

          {isEditing ? (
            <button
              onClick={handleSave}
              className="btn btn-primary !py-1.5 !px-3 text-xs rounded-full"
            >
              <Save size={14} /> Save Edit
            </button>
          ) : (
            <button
              onClick={() => setIsEditing(true)}
              className="btn btn-ghost !py-1.5 !px-3 text-xs rounded-full text-muted hover:text-ink"
            >
              <Edit3 size={13} /> Edit Inline
            </button>
          )}
        </div>

        <button
          onClick={() => setShowRegenModal(true)}
          disabled={isRegenerating}
          className="btn btn-ghost !py-1.5 !px-3 text-xs rounded-full text-muted hover:text-ink"
          title="Regenerate this question with AI"
        >
          <RotateCw size={13} className={isRegenerating ? "animate-spin" : ""} />
          <span>Regenerate</span>
        </button>
      </div>

      {/* Regeneration Modal */}
      {showRegenModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="glass w-full max-w-lg p-6 space-y-4 border border-line shadow-2xl bg-[var(--bg-elev)]">
            <h3 className="text-lg font-semibold text-ink">Regenerate Question {question.slot_no}</h3>
            <p className="text-xs text-muted">
              You can provide optional instructions to guide the AI regeneration (e.g. "Focus on numerical calculation with units" or "Make it simpler").
            </p>
            <textarea
              className="field w-full text-sm"
              rows={3}
              placeholder="e.g. Focus on experimental observation in Activity 1.1..."
              value={regenInstruction}
              onChange={(e) => setRegenInstruction(e.target.value)}
            />
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRegenModal(false)}
                className="btn btn-ghost text-xs"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleRegenSubmit}
                disabled={isRegenerating}
                className="btn btn-primary text-xs"
              >
                {isRegenerating ? "Regenerating..." : "Regenerate Now"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
