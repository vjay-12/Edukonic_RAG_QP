export interface Chapter {
  chapter_no: number;
  chapter_title: string;
  page_count: number;
  chunks_count: number;
  status: string;
}

export interface SectionConfig {
  id: string;
  name?: string;
  type: string;
  count: number;
  marks: number;
}

export interface ChapterWeight {
  chapter_no: number;
  weight: number;
}

export interface PaperConfig {
  title: string;
  class: number;
  subject: string;
  total_marks?: number;
  chapters: ChapterWeight[];
  sections: SectionConfig[];
  difficulty_mix: {
    easy: number;
    medium: number;
    hard: number;
  };
  competency_percent: number;
  avoid_duplicates_from_bank: boolean;
  header: {
    school_name: string;
    exam_name: string;
    date: string;
    duration: string;
    instructions: string[];
  };
}

export interface QuestionData {
  id: number;
  slot_no: number;
  section: string;
  type: string;
  marks: number;
  chapter_no: number;
  topic?: string;
  difficulty?: string;
  competency: boolean;
  bloom?: string;
  content: {
    stem: string;
    options?: string[];
    correct_option?: string;
    sub_questions?: { stem: string; marks: number; answer: string }[];
    answer: string;
    marking_scheme?: { step: string; marks: number }[];
    source?: { chunk_ids: number[]; pages: number[] };
  };
  source_chunk_ids?: number[];
  validation?: {
    grounded: boolean;
    answer_correct: boolean;
    marks_fit: boolean;
    single_correct_option: boolean;
    issues: string[];
    verdict: "pass" | "warn" | "fail";
  };
  status: "draft" | "accepted" | "rejected";
}

export interface BlueprintReport {
  total_marks: number;
  question_count: number;
  marks_by_chapter: Record<string, number>;
  count_by_type: Record<string, number>;
  difficulty_split: Record<string, number>;
  competency_count: number;
  competency_percent: number;
  flagged_count: number;
}

export interface PaperDetail {
  id: number;
  title: string;
  config: PaperConfig;
  status: "queued" | "planning" | "generating" | "validating" | "ready" | "failed";
  progress: number;
  error?: string;
  created_at: string;
  questions: QuestionData[];
  blueprint_report?: BlueprintReport;
}

export interface PaperListItem {
  id: number;
  title: string;
  total_marks: number;
  question_count: number;
  status: string;
  progress: number;
  created_at: string;
}

export interface ChunkCitation {
  id: number;
  chapter_no: number;
  chapter_title: string;
  page_start: number;
  page_end: number;
  section_heading: string;
  content_type: string;
  token_count: number;
  text: string;
  citation: string;
}

export interface BankQuestion {
  id: number;
  class: number;
  subject: string;
  chapter_no: number;
  type: string;
  marks: number;
  difficulty?: string;
  competency: boolean;
  content: any;
  approved_at: string;
}

const API_BASE = "/api";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/health`);
  return res.json();
}

export async function login(password: string): Promise<{ token: string; authenticated: boolean }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Authentication failed");
  }
  return res.json();
}

export async function fetchChapters(): Promise<Chapter[]> {
  const res = await fetch(`${API_BASE}/chapters`);
  if (!res.ok) throw new Error("Failed to load chapters");
  return res.json();
}

export async function fetchBlueprints(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/blueprints`);
  if (!res.ok) throw new Error("Failed to load blueprints");
  return res.json();
}

export async function createPaper(config: PaperConfig): Promise<{ id: number }> {
  const res = await fetch(`${API_BASE}/papers`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to create paper");
  }
  return res.json();
}

export async function fetchPapers(): Promise<PaperListItem[]> {
  const res = await fetch(`${API_BASE}/papers`);
  if (!res.ok) throw new Error("Failed to load papers");
  return res.json();
}

export async function fetchPaperDetail(paperId: number | string): Promise<PaperDetail> {
  const res = await fetch(`${API_BASE}/papers/${paperId}`);
  if (!res.ok) throw new Error("Failed to load paper detail");
  return res.json();
}

export async function updateQuestionStatus(
  paperId: number | string,
  questionId: number,
  status: "accepted" | "rejected" | "draft"
) {
  const res = await fetch(`${API_BASE}/papers/${paperId}/questions/${questionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  if (!res.ok) throw new Error("Failed to update status");
  return res.json();
}

export async function updateQuestionContent(
  paperId: number | string,
  questionId: number,
  content: any
) {
  const res = await fetch(`${API_BASE}/papers/${paperId}/questions/${questionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) throw new Error("Failed to update content");
  return res.json();
}

export async function regenerateQuestion(
  paperId: number | string,
  questionId: number,
  instruction?: string
) {
  const res = await fetch(`${API_BASE}/papers/${paperId}/questions/${questionId}/regenerate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ instruction }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Regeneration failed");
  }
  return res.json();
}

export async function finalizePaper(paperId: number | string) {
  const res = await fetch(`${API_BASE}/papers/${paperId}/finalize`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to finalize paper");
  return res.json();
}

export async function fetchChunkCitation(chunkId: number): Promise<ChunkCitation> {
  const res = await fetch(`${API_BASE}/chunks/${chunkId}`);
  if (!res.ok) throw new Error("Failed to load citation");
  return res.json();
}

export async function fetchQuestionBank(filters?: {
  chapter?: number;
  type?: string;
  marks?: number;
  difficulty?: string;
}): Promise<BankQuestion[]> {
  const params = new URLSearchParams();
  if (filters?.chapter) params.append("chapter", filters.chapter.toString());
  if (filters?.type) params.append("type", filters.type);
  if (filters?.marks) params.append("marks", filters.marks.toString());
  if (filters?.difficulty) params.append("difficulty", filters.difficulty);

  const res = await fetch(`${API_BASE}/bank?${params.toString()}`);
  if (!res.ok) throw new Error("Failed to load question bank");
  return res.json();
}

export async function downloadPaperDocx(
  paperId: number | string,
  part: "paper" | "key" = "paper"
): Promise<string> {
  const url = `${API_BASE}/papers/${paperId}/export?format=docx&part=${part}`;
  const res = await fetch(url);

  if (!res.ok) {
    let errMsg = `Export failed with status ${res.status}`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        errMsg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      try {
        const text = await res.text();
        if (text) errMsg = text;
      } catch {
        // fallback
      }
    }
    throw new Error(errMsg);
  }

  // Determine filename from Content-Disposition header or fallback
  let filename = part === "key" ? `Answer_Key_Paper_${paperId}.docx` : `Paper_${paperId}.docx`;
  const disposition = res.headers.get("content-disposition");
  if (disposition) {
    const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
    if (match && match[1]) {
      filename = match[1].replace(/['"]/g, "").trim();
    }
  }

  const blob = await res.blob();
  const blobUrl = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = blobUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(blobUrl);

  return filename;
}

