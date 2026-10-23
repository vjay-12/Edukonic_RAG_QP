import React, { useState } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Download, Printer, ArrowLeft, FileText, CheckCircle2 } from "lucide-react";
import { fetchPaperDetail } from "../api/client";

export const PaperPreview: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [activeTab, setActiveTab] = useState<"paper" | "key">("paper");

  const paperId = id ? parseInt(id) : 0;
  const { data: paper, isLoading } = useQuery({
    queryKey: ["paper", paperId],
    queryFn: () => fetchPaperDetail(paperId),
  });

  if (isLoading || !paper) {
    return <div className="text-center py-24 text-muted">Loading preview...</div>;
  }

  const config = paper.config || {};
  const header = config.header || {};
  const schoolName = header.school_name || "Edukonic Model Senior Secondary School";
  const examName = header.exam_name || paper.title;
  const duration = header.duration || "1 Hour";
  const instructions = header.instructions || [];
  const totalMarks = config.total_marks || paper.questions.reduce((s, q) => s + q.marks, 0);

  // Group by section
  const sectionsMap: Record<string, typeof paper.questions> = {};
  paper.questions.forEach((q) => {
    if (!sectionsMap[q.section]) sectionsMap[q.section] = [];
    sectionsMap[q.section].push(q);
  });

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="mx-auto max-w-4xl px-6 py-8 space-y-6">
      {/* Top Action Bar (hidden in print) */}
      <div className="flex flex-wrap items-center justify-between gap-4 print:hidden border-b border-line pb-4">
        <Link to={`/papers/${paperId}`} className="text-xs text-muted hover:text-white flex items-center gap-1.5">
          <ArrowLeft size={14} /> Back to Review & Editing
        </Link>

        {/* Tab Switcher */}
        <div className="flex gap-1 bg-[var(--surface)] p-1 rounded-full border border-line">
          <button
            onClick={() => setActiveTab("paper")}
            className={`px-4 py-1.5 text-xs rounded-full transition-colors cursor-pointer ${
              activeTab === "paper" ? "bg-white text-black font-semibold" : "text-muted hover:text-white"
            }`}
          >
            Question Paper
          </button>
          <button
            onClick={() => setActiveTab("key")}
            className={`px-4 py-1.5 text-xs rounded-full transition-colors cursor-pointer ${
              activeTab === "key" ? "bg-white text-black font-semibold" : "text-muted hover:text-white"
            }`}
          >
            Marking Scheme & Key
          </button>
        </div>

        {/* Downloads */}
        <div className="flex items-center gap-2">
          <a
            href={`/api/papers/${paperId}/export?part=paper`}
            className="btn btn-ghost !py-1.5 !px-3 text-xs rounded-full"
            download
          >
            <Download size={13} /> Paper DOCX
          </a>
          <a
            href={`/api/papers/${paperId}/export?part=key`}
            className="btn btn-ghost !py-1.5 !px-3 text-xs rounded-full"
            download
          >
            <Download size={13} /> Key DOCX
          </a>
          <button
            onClick={handlePrint}
            className="btn btn-primary !py-1.5 !px-3 text-xs rounded-full"
          >
            <Printer size={13} /> Print / Save PDF
          </button>
        </div>
      </div>

      {/* Print Paper Document */}
      <div className="bg-white text-black p-8 sm:p-12 rounded-xl shadow-xl print:p-0 print:shadow-none font-serif leading-normal">
        {/* Document Header */}
        <div className="text-center border-b-2 border-black pb-4 mb-6">
          <h1 className="text-2xl font-bold uppercase tracking-wide">{schoolName}</h1>
          <h2 className="text-lg font-semibold mt-1">
            {activeTab === "paper" ? examName : `${examName} — ANSWER KEY & MARKING SCHEME`}
          </h2>
          <div className="flex justify-between text-xs font-sans font-medium mt-3 px-2">
            <span>Class: {config.class || 10}</span>
            <span>Subject: {config.subject || "Science"}</span>
            <span>Time: {duration}</span>
            <span>Max Marks: {totalMarks}</span>
          </div>
        </div>

        {/* Instructions (Only on paper tab) */}
        {activeTab === "paper" && instructions.length > 0 && (
          <div className="mb-6 pb-4 border-b border-gray-300 font-sans text-xs">
            <h3 className="font-bold mb-1.5 uppercase tracking-wider text-gray-700">General Instructions:</h3>
            <ul className="list-disc list-inside space-y-1 text-gray-800">
              {instructions.map((ins: string, idx: number) => (
                <li key={idx}>{ins}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Tab 1: Question Paper View */}
        {activeTab === "paper" && (
          <div className="space-y-8 font-sans">
            {Object.entries(sectionsMap).map(([sec, qList]) => {
              const marksEach = qList[0]?.marks || 1;
              return (
                <div key={sec} className="space-y-4">
                  <div className="text-center font-bold text-sm tracking-wide border-b border-black/20 pb-1 mb-3">
                    SECTION {sec} ({marksEach} Mark{marksEach > 1 ? "s" : ""} each)
                  </div>

                  <div className="space-y-5">
                    {qList.map((q) => {
                      const c = q.content || {};
                      return (
                        <div key={q.id} className="text-sm">
                          <div className="flex justify-between items-start gap-4">
                            <span className="font-semibold text-gray-900 leading-relaxed">
                              Q{q.slot_no}. {c.stem}
                            </span>
                            <span className="font-mono text-xs font-bold shrink-0">[{q.marks}]</span>
                          </div>

                          {/* MCQ Options */}
                          {c.options && Array.isArray(c.options) && (
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-2 ml-4">
                              {c.options.map((opt: string, i: number) => {
                                const letter = String.fromCharCode(65 + i);
                                return (
                                  <div key={i} className="text-xs text-gray-800">
                                    <span className="font-bold mr-1">({letter})</span>
                                    <span>{opt}</span>
                                  </div>
                                );
                              })}
                            </div>
                          )}

                          {/* Case Sub-questions */}
                          {c.sub_questions && Array.isArray(c.sub_questions) && (
                            <div className="space-y-2 mt-2 ml-4 border-l-2 border-gray-200 pl-3">
                              {c.sub_questions.map((sq: any, i: number) => (
                                <div key={i} className="text-xs text-gray-800 flex justify-between">
                                  <span>
                                    ({i + 1}) {sq.stem}
                                  </span>
                                  <span className="font-mono font-semibold ml-2">[{sq.marks}]</span>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Tab 2: Answer Key & Marking Scheme View */}
        {activeTab === "key" && (
          <div className="space-y-6 font-sans text-xs">
            {paper.questions.map((q) => {
              const c = q.content || {};
              const pages = c.source?.pages || [];
              const pageRef = pages.length > 0 ? `NCERT pp. ${Math.min(...pages)}–${Math.max(...pages)}` : "NCERT";

              return (
                <div key={q.id} className="p-4 border border-gray-200 rounded-lg space-y-2">
                  <div className="flex justify-between items-center font-bold text-gray-900 border-b border-gray-100 pb-1">
                    <span>Q{q.slot_no} [Section {q.section} · {q.type.toUpperCase()} · {q.marks} Mark{q.marks > 1 ? "s" : ""}]</span>
                    <span className="text-gray-500 font-normal italic">{pageRef}</span>
                  </div>

                  {c.correct_option && (
                    <div className="font-semibold text-emerald-800">
                      Correct Option: ({c.correct_option})
                    </div>
                  )}

                  <div>
                    <strong className="text-gray-600 block mb-0.5">Model Answer:</strong>
                    <div className="text-gray-800 whitespace-pre-wrap">{c.answer}</div>
                  </div>

                  {c.marking_scheme && Array.isArray(c.marking_scheme) && c.marking_scheme.length > 0 && (
                    <div className="bg-gray-50 p-2.5 rounded">
                      <strong className="text-gray-600 block mb-1">Marking Scheme:</strong>
                      <ul className="list-disc list-inside space-y-0.5 text-gray-700">
                        {c.marking_scheme.map((step: any, idx: number) => (
                          <li key={idx}>
                            <span>{step.step}</span>
                            <span className="font-mono font-semibold text-gray-900 ml-2">[{step.marks} mark]</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
