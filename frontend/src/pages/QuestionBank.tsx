import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Database, Filter, BookOpen, Layers, CheckCircle2 } from "lucide-react";
import { fetchQuestionBank, BankQuestion } from "../api/client";

export const QuestionBank: React.FC = () => {
  const [filterChapter, setFilterChapter] = useState<number | undefined>(undefined);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [filterDifficulty, setFilterDifficulty] = useState<string | undefined>(undefined);

  const { data: questions = [], isLoading } = useQuery({
    queryKey: ["bank", filterChapter, filterType, filterDifficulty],
    queryFn: () =>
      fetchQuestionBank({
        chapter: filterChapter,
        type: filterType,
        difficulty: filterDifficulty,
      }),
  });

  return (
    <div className="mx-auto max-w-5xl px-6 py-10 space-y-8">
      <div className="border-b border-line pb-6">
        <h1 className="display text-4xl text-ink font-normal flex items-center gap-3">
          <Database size={28} className="text-blue-500 dark:text-blue-400" />
          <span>Question Bank</span>
        </h1>
        <p className="text-sm text-muted mt-1">
          Repository of teacher-approved CBSE examination items saved from finalized papers. Used for automated deduplication and future blueprint planning.
        </p>
      </div>

      {/* Filter Bar */}
      <div className="glass p-4 flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-xs text-muted font-medium flex items-center gap-1.5">
            <Filter size={13} /> Filters:
          </span>

          <select
            className="field !w-auto !py-1 text-xs"
            value={filterChapter ?? ""}
            onChange={(e) => setFilterChapter(e.target.value ? parseInt(e.target.value) : undefined)}
          >
            <option value="">All Chapters</option>
            <option value="1">Ch 1: Chemical Reactions</option>
            <option value="5">Ch 5: Life Processes</option>
            <option value="11">Ch 11: Electricity</option>
          </select>

          <select
            className="field !w-auto !py-1 text-xs"
            value={filterType ?? ""}
            onChange={(e) => setFilterType(e.target.value || undefined)}
          >
            <option value="">All Types</option>
            <option value="mcq">MCQ</option>
            <option value="assertion_reason">Assertion-Reason</option>
            <option value="vsa">VSA (2m)</option>
            <option value="sa">SA (3m)</option>
            <option value="la">LA (5m)</option>
            <option value="case">Case-Based (4m)</option>
          </select>

          <select
            className="field !w-auto !py-1 text-xs"
            value={filterDifficulty ?? ""}
            onChange={(e) => setFilterDifficulty(e.target.value || undefined)}
          >
            <option value="">All Difficulties</option>
            <option value="easy">Easy</option>
            <option value="medium">Medium</option>
            <option value="hard">Hard</option>
          </select>
        </div>

        <div className="text-xs text-muted font-mono">
          {questions.length} Approved Items
        </div>
      </div>

      {/* Questions List */}
      {isLoading ? (
        <div className="text-center py-20 text-muted">Loading question bank...</div>
      ) : questions.length === 0 ? (
        <div className="glass p-12 text-center space-y-3">
          <Database size={32} className="mx-auto text-muted opacity-50" />
          <h3 className="text-base font-semibold text-ink">No questions found</h3>
          <p className="text-xs text-muted max-w-sm mx-auto">
            When you finalize a generated question paper, accepted questions will appear here automatically.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {questions.map((q: BankQuestion) => {
            const c = q.content || {};
            return (
              <div key={q.id} className="glass p-5 border border-line space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="chip text-xs">Ch {q.chapter_no}</span>
                    <span className="chip text-xs uppercase font-mono">{q.type}</span>
                    <span className="chip text-xs font-semibold">{q.marks} Mark{q.marks > 1 ? "s" : ""}</span>
                    {q.difficulty && <span className="chip text-xs capitalize">{q.difficulty}</span>}
                    {q.competency && (
                      <span className="chip text-xs text-sky-500 dark:text-sky-400 border-sky-500/30 bg-sky-500/10">
                        Competency
                      </span>
                    )}
                  </div>
                  <span className="text-xs text-muted font-mono">
                    Approved: {new Date(q.approved_at).toLocaleDateString()}
                  </span>
                </div>

                <p className="text-sm text-ink font-medium leading-relaxed">{c.stem}</p>

                {c.options && Array.isArray(c.options) && (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs pl-2">
                    {c.options.map((opt: string, i: number) => {
                      const letter = String.fromCharCode(65 + i);
                      const isCorrect = c.correct_option === letter;
                      return (
                        <div
                          key={i}
                          className={`p-2 rounded border ${
                            isCorrect
                              ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300 font-semibold"
                              : "border-line bg-[var(--surface)] text-ink"
                          }`}
                        >
                          ({letter}) {opt}
                        </div>
                      );
                    })}
                  </div>
                )}

                <div className="pt-2 border-t border-line text-xs text-muted flex items-center justify-between">
                  <div>
                    <strong className="text-muted">Answer:</strong> <span className="text-ink">{c.answer}</span>
                  </div>
                  {c.source?.pages && (
                    <span className="italic">
                      NCERT pp. {Math.min(...c.source.pages)}–{Math.max(...c.source.pages)}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
