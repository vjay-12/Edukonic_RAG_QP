import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Sparkles, ArrowRight, Layers, Sliders, FileText, CheckCircle2, AlertTriangle } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchChapters, fetchBlueprints, createPaper, PaperConfig } from "../api/client";

export const Generate: React.FC = () => {
  const navigate = useNavigate();

  // Queries
  const { data: chapters = [], isLoading: loadingChapters } = useQuery({
    queryKey: ["chapters"],
    queryFn: fetchChapters,
  });

  const { data: blueprints = [] } = useQuery({
    queryKey: ["blueprints"],
    queryFn: fetchBlueprints,
  });

  // State
  const [selectedPresetId, setSelectedPresetId] = useState<string>("unit_test_25");
  const [title, setTitle] = useState("Unit Test 1 - Class 10 Science");
  const [selectedChapters, setSelectedChapters] = useState<number[]>([1, 5, 11]);
  const [chapterWeights, setChapterWeights] = useState<Record<number, number>>({ 1: 0.4, 5: 0.3, 11: 0.3 });

  const [sections, setSections] = useState([
    { id: "A", name: "Section A", type: "mcq", count: 6, marks: 1 },
    { id: "B", name: "Section B", type: "vsa", count: 2, marks: 2 },
    { id: "C", name: "Section C", type: "sa", count: 2, marks: 3 },
    { id: "D", name: "Section D", type: "la", count: 1, marks: 5 },
    { id: "E", name: "Section E", type: "case", count: 1, marks: 4 },
  ]);

  const [diffMix, setDiffMix] = useState({ easy: 30, medium: 50, hard: 20 });
  const [competencyPercent, setCompetencyPercent] = useState(40);
  const [avoidBankDedupe, setAvoidBankDedupe] = useState(true);

  // Header state
  const [schoolName, setSchoolName] = useState("Edukonic Model Senior Secondary School");
  const [examName, setExamName] = useState("Periodic Assessment / Unit Test 1 (2026-27)");
  const [duration, setDuration] = useState("1 Hour");
  const [instructions, setInstructions] = useState(
    "All questions are compulsory.\nSection A consists of 6 questions of 1 mark each.\nSection B consists of 2 Very Short Answer questions of 2 marks each.\nSection C consists of 2 Short Answer questions of 3 marks each.\nSection D consists of 1 Long Answer question of 5 marks.\nSection E consists of 1 Case-based question of 4 marks."
  );

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // Apply blueprint preset selection
  const handleSelectPreset = (preset: any) => {
    setSelectedPresetId(preset.preset_id);
    setTitle(preset.title || title);
    if (preset.sections) setSections(preset.sections);
    if (preset.difficulty_mix) {
      setDiffMix({
        easy: Math.round((preset.difficulty_mix.easy || 0.3) * 100),
        medium: Math.round((preset.difficulty_mix.medium || 0.5) * 100),
        hard: Math.round((preset.difficulty_mix.hard || 0.2) * 100),
      });
    }
    if (preset.competency_percent !== undefined) setCompetencyPercent(preset.competency_percent);
    if (preset.header) {
      if (preset.header.school_name) setSchoolName(preset.header.school_name);
      if (preset.header.exam_name) setExamName(preset.header.exam_name);
      if (preset.header.duration) setDuration(preset.header.duration);
      if (preset.header.instructions) setInstructions(preset.header.instructions.join("\n"));
    }
  };

  // Live total marks calculation
  const calculatedTotalMarks = sections.reduce((sum, sec) => sum + sec.count * sec.marks, 0);
  const totalQuestions = sections.reduce((sum, sec) => sum + sec.count, 0);

  // Chapter weight normalization
  const toggleChapter = (chNo: number) => {
    let next: number[];
    if (selectedChapters.includes(chNo)) {
      if (selectedChapters.length <= 1) return; // Keep at least one
      next = selectedChapters.filter((c) => c !== chNo);
    } else {
      next = [...selectedChapters, chNo];
    }
    setSelectedChapters(next);

    // Rebalance weights evenly
    const evenWeight = Number((1.0 / next.length).toFixed(2));
    const newWeights: Record<number, number> = {};
    next.forEach((c) => (newWeights[c] = evenWeight));
    setChapterWeights(newWeights);
  };

  const handleWeightChange = (chNo: number, val: number) => {
    setChapterWeights((prev) => ({ ...prev, [chNo]: val }));
  };

  const handleSectionChange = (index: number, field: string, val: any) => {
    setSections((prev) => {
      const copy = [...prev];
      copy[index] = { ...copy[index], [field]: val };
      return copy;
    });
  };

  const handleAddSection = () => {
    const nextLetter = String.fromCharCode(65 + sections.length);
    setSections([
      ...sections,
      { id: nextLetter, name: `Section ${nextLetter}`, type: "sa", count: 1, marks: 3 },
    ]);
  };

  const handleRemoveSection = (index: number) => {
    if (sections.length <= 1) return;
    setSections(sections.filter((_, i) => i !== index));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMessage("");

    try {
      // Normalize weights
      const totalW = selectedChapters.reduce((sum, ch) => sum + (chapterWeights[ch] || 0), 0);
      const chWeights = selectedChapters.map((ch) => ({
        chapter_no: ch,
        weight: totalW > 0 ? Number(((chapterWeights[ch] || 0) / totalW).toFixed(2)) : 1.0 / selectedChapters.length,
      }));

      // Adjust last chapter so sum is exactly 1.0
      const currentSum = chWeights.reduce((s, c) => s + c.weight, 0);
      if (chWeights.length > 0 && Math.abs(currentSum - 1.0) > 0.001) {
        chWeights[chWeights.length - 1].weight = Number(
          (chWeights[chWeights.length - 1].weight + (1.0 - currentSum)).toFixed(2)
        );
      }

      const diffTotal = diffMix.easy + diffMix.medium + diffMix.hard || 100;
      const config: PaperConfig = {
        title,
        class: 10,
        subject: "Science",
        total_marks: calculatedTotalMarks,
        chapters: chWeights,
        sections,
        difficulty_mix: {
          easy: Number((diffMix.easy / diffTotal).toFixed(2)),
          medium: Number((diffMix.medium / diffTotal).toFixed(2)),
          hard: Number((diffMix.hard / diffTotal).toFixed(2)),
        },
        competency_percent: competencyPercent,
        avoid_duplicates_from_bank: avoidBankDedupe,
        header: {
          school_name: schoolName,
          exam_name: examName,
          date: new Date().toLocaleDateString("en-US", { month: "short", year: "numeric" }),
          duration,
          instructions: instructions.split("\n").filter((line) => line.trim().length > 0),
        },
      };

      const result = await createPaper(config);
      navigate(`/papers/${result.id}`);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to generate paper");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="mx-auto max-w-5xl px-6 py-12 space-y-12">
      {/* Hero Header */}
      <div>
        <span className="chip">
          <Sparkles size={14} className="text-blue-400" /> New · AI question paper generator
        </span>
        <h1 className="display mt-6 text-5xl md:text-6xl text-white">
          Board-ready papers, <span className="grad-blue">grounded</span> in your{" "}
          <span className="grad-pink">NCERT</span> books.
        </h1>
        <p className="mt-4 max-w-2xl text-lg text-muted">
          Pick syllabus chapters, customize sections and difficulty, and generate a validated question paper complete with model answers, marking scheme, and verified textbook citations.
        </p>
      </div>

      {errorMessage && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-300 flex items-center gap-3">
          <AlertTriangle size={18} className="shrink-0" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Configuration Form */}
      <form onSubmit={handleSubmit} className="space-y-8">
        {/* Preset Selector */}
        <section className="glass p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-white flex items-center gap-2">
              <Layers size={18} className="text-blue-400" />
              <span>Blueprint Presets</span>
            </h2>
            <span className="text-xs text-muted">Choose a standard CBSE framework</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {blueprints.map((b) => (
              <div
                key={b.preset_id}
                onClick={() => handleSelectPreset(b)}
                className={`p-4 rounded-xl border cursor-pointer transition-all ${
                  selectedPresetId === b.preset_id
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-line bg-[var(--surface)] hover:bg-[var(--surface-hover)]"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-semibold text-white">{b.title}</h3>
                  <span className="chip text-xs font-mono">{b.total_marks || "N/A"} Marks</span>
                </div>
                <p className="text-xs text-muted">
                  {b.sections?.length || 0} Sections · {b.sections?.reduce((s: number, x: any) => s + x.count, 0) || 0} Questions · {b.competency_percent}% Competency
                </p>
              </div>
            ))}
          </div>
        </section>

        {/* Paper Details */}
        <section className="glass p-6 space-y-4">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <FileText size={18} className="text-purple-400" />
            <span>Paper Information</span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted">Paper Title</label>
              <input
                className="field text-sm"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted">Examination / Assessment Name</label>
              <input
                className="field text-sm"
                value={examName}
                onChange={(e) => setExamName(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted">School / Institution Name</label>
              <input
                className="field text-sm"
                value={schoolName}
                onChange={(e) => setSchoolName(e.target.value)}
              />
            </div>
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted">Exam Duration</label>
              <input
                className="field text-sm"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
              />
            </div>
            <div className="space-y-1.5 md:col-span-2">
              <label className="text-xs font-medium text-muted">General Instructions (one per line)</label>
              <textarea
                className="field text-xs font-mono"
                rows={4}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
              />
            </div>
          </div>
        </section>

        {/* Chapter Selection & Weighting */}
        <section className="glass p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xl font-semibold text-white flex items-center gap-2">
              <CheckCircle2 size={18} className="text-emerald-400" />
              <span>Syllabus Chapters ({selectedChapters.length} Selected)</span>
            </h2>
            <span className="text-xs text-muted">Weights are normalized automatically</span>
          </div>

          {loadingChapters ? (
            <div className="text-center py-6 text-sm text-muted">Loading ingested chapters...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {chapters.map((ch) => {
                const isSelected = selectedChapters.includes(ch.chapter_no);
                return (
                  <div
                    key={ch.chapter_no}
                    className={`p-4 rounded-xl border transition-all ${
                      isSelected
                        ? "border-emerald-500/50 bg-emerald-950/10"
                        : "border-line bg-[var(--surface)] opacity-60"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <label className="flex items-center gap-2.5 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleChapter(ch.chapter_no)}
                          className="rounded text-emerald-500 focus:ring-0"
                        />
                        <span className="font-semibold text-sm text-white">
                          Ch {ch.chapter_no}: {ch.chapter_title}
                        </span>
                      </label>
                    </div>
                    <div className="text-xs text-muted flex items-center justify-between mt-2">
                      <span>{ch.chunks_count} chunks embedded</span>
                      {isSelected && (
                        <div className="flex items-center gap-1.5">
                          <span>Weight:</span>
                          <input
                            type="number"
                            step="0.05"
                            min="0.1"
                            max="1.0"
                            className="field !w-16 !p-1 text-xs text-center font-mono"
                            value={chapterWeights[ch.chapter_no] ?? 0.3}
                            onChange={(e) => handleWeightChange(ch.chapter_no, parseFloat(e.target.value) || 0.1)}
                          />
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Sections & Question Types */}
        <section className="glass p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-semibold text-white">Sections & Marks Distribution</h2>
              <p className="text-xs text-muted mt-0.5">
                Total Questions: <strong className="text-white">{totalQuestions}</strong> · Total Marks:{" "}
                <strong className="text-emerald-400 font-mono text-sm">{calculatedTotalMarks}</strong>
              </p>
            </div>
            <button
              type="button"
              onClick={handleAddSection}
              className="btn btn-ghost !py-1.5 !px-3 text-xs rounded-full"
            >
              + Add Section
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-line text-muted text-xs">
                  <th className="pb-3 font-medium">Sec</th>
                  <th className="pb-3 font-medium">Question Type</th>
                  <th className="pb-3 font-medium">Count</th>
                  <th className="pb-3 font-medium">Marks / Q</th>
                  <th className="pb-3 font-medium">Subtotal</th>
                  <th className="pb-3 text-right"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {sections.map((sec, idx) => (
                  <tr key={idx} className="group">
                    <td className="py-2.5 font-bold font-mono text-white">{sec.id}</td>
                    <td className="py-2.5">
                      <select
                        className="field !py-1 text-xs"
                        value={sec.type}
                        onChange={(e) => handleSectionChange(idx, "type", e.target.value)}
                      >
                        <option value="mcq">MCQ (Multiple Choice)</option>
                        <option value="assertion_reason">Assertion-Reason</option>
                        <option value="vsa">Very Short Answer (VSA)</option>
                        <option value="sa">Short Answer (SA)</option>
                        <option value="la">Long Answer (LA)</option>
                        <option value="case">Case-Based Assessment</option>
                      </select>
                    </td>
                    <td className="py-2.5">
                      <input
                        type="number"
                        min="1"
                        max="30"
                        className="field !w-20 !py-1 text-xs font-mono"
                        value={sec.count}
                        onChange={(e) => handleSectionChange(idx, "count", parseInt(e.target.value) || 1)}
                      />
                    </td>
                    <td className="py-2.5">
                      <input
                        type="number"
                        min="1"
                        max="10"
                        className="field !w-20 !py-1 text-xs font-mono"
                        value={sec.marks}
                        onChange={(e) => handleSectionChange(idx, "marks", parseInt(e.target.value) || 1)}
                      />
                    </td>
                    <td className="py-2.5 font-mono text-white font-semibold">
                      {sec.count * sec.marks} marks
                    </td>
                    <td className="py-2.5 text-right">
                      <button
                        type="button"
                        onClick={() => handleRemoveSection(idx)}
                        className="text-xs text-muted hover:text-rose-400 p-1"
                      >
                        Remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        {/* Difficulty Mix & Competency */}
        <section className="glass p-6 space-y-6">
          <h2 className="text-xl font-semibold text-white flex items-center gap-2">
            <Sliders size={18} className="text-pink-400" />
            <span>Difficulty Mix & Competency Focus</span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-medium">
                <span className="text-emerald-400">Easy Questions</span>
                <span className="font-mono">{diffMix.easy}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={diffMix.easy}
                onChange={(e) => setDiffMix({ ...diffMix, easy: parseInt(e.target.value) })}
                className="w-full accent-emerald-500 cursor-pointer"
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs font-medium">
                <span className="text-blue-400">Medium Questions</span>
                <span className="font-mono">{diffMix.medium}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={diffMix.medium}
                onChange={(e) => setDiffMix({ ...diffMix, medium: parseInt(e.target.value) })}
                className="w-full accent-blue-500 cursor-pointer"
              />
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs font-medium">
                <span className="text-rose-400">Hard Questions</span>
                <span className="font-mono">{diffMix.hard}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={diffMix.hard}
                onChange={(e) => setDiffMix({ ...diffMix, hard: parseInt(e.target.value) })}
                className="w-full accent-rose-500 cursor-pointer"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 border-t border-line">
            <div className="space-y-2">
              <div className="flex justify-between text-xs font-medium">
                <span className="text-sky-300">Competency-Based Assessment Target</span>
                <span className="font-mono">{competencyPercent}%</span>
              </div>
              <input
                type="range"
                min="0"
                max="100"
                step="5"
                value={competencyPercent}
                onChange={(e) => setCompetencyPercent(parseInt(e.target.value))}
                className="w-full accent-sky-500 cursor-pointer"
              />
              <p className="text-xs text-muted">
                CBSE guidelines target 40–50% application-based practical reasoning questions.
              </p>
            </div>

            <div className="flex items-center gap-3 pt-4">
              <input
                type="checkbox"
                id="avoidBank"
                checked={avoidBankDedupe}
                onChange={(e) => setAvoidBankDedupe(e.target.checked)}
                className="rounded text-blue-500 focus:ring-0 cursor-pointer"
              />
              <label htmlFor="avoidBank" className="text-xs text-gray-300 cursor-pointer">
                <strong>Avoid duplicates from Question Bank:</strong> Automatically cross-references previously approved examination items using vector similarity to prevent repeated questions.
              </label>
            </div>
          </div>
        </section>

        {/* Submit Button */}
        <div className="flex items-center justify-between pt-4">
          <div className="text-sm text-muted">
            Ready to generate <strong className="text-white">{totalQuestions} questions</strong> ({calculatedTotalMarks} marks total).
          </div>
          <button
            type="submit"
            disabled={isSubmitting || totalQuestions === 0}
            className="btn btn-primary !py-3.5 !px-8 text-base shadow-lg shadow-blue-500/10 cursor-pointer"
          >
            {isSubmitting ? "Initiating Generation..." : "Generate Question Paper"}
            <ArrowRight size={18} />
          </button>
        </div>
      </form>
    </div>
  );
};
