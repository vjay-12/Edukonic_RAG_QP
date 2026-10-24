// Utility functions for chemical formula subscripts, option prefix stripping, and sub-question numbering

const ELEMENTS_REGEX =
  "(?:H|He|Li|Be|B|C|N|O|F|Ne|Na|Mg|Al|Si|P|S|Cl|Ar|K|Ca|Cr|Mn|Fe|Co|Ni|Cu|Zn|Br|Ag|Sn|I|Ba|Pt|Au|Hg|Pb|\\))";

const SUB_MAP: Record<string, string> = {
  "0": "₀",
  "1": "₁",
  "2": "₂",
  "3": "₃",
  "4": "₄",
  "5": "₅",
  "6": "₆",
  "7": "₇",
  "8": "₈",
  "9": "₉",
};

const ROMAN_NUMERALS = ["(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)", "(vii)", "(viii)"];

export function formatMarks(marks?: number | string): string {
  if (marks === undefined || marks === null) return "";
  const num = typeof marks === "string" ? parseFloat(marks) : marks;
  const numInt = num === Math.floor(num) ? Math.floor(num) : num;
  return numInt === 1 ? "1 mark" : `${numInt} marks`;
}

const SUB_MAP_SUPER: Record<string, string> = {
  "0": "⁰",
  "1": "¹",
  "2": "²",
  "3": "³",
  "4": "⁴",
  "5": "⁵",
  "6": "⁶",
  "7": "⁷",
  "8": "⁸",
  "9": "⁹",
};

export function formatChemicalFormulas(text?: string): string {
  if (!text) return "";

  // 1. Arrow notations
  let formatted = text
    .replace(/—\s*\(([^\)]+)\)\s*→/g, " → ($1) ")
    .replace(/\-\s*\(([^\)]+)\)\s*\->/g, " → ($1) ")
    .replace(/\-\s*\[([^\]]+)\]\s*\->/g, " → [$1] ")
    .replace(/(\-\->|\->|==>)/g, " → ")
    .replace(/(<=>|<-->)/g, " ⇌ ");

  // 2. Chemical elements subscripts
  const pattern = new RegExp(`(${ELEMENTS_REGEX})(\\d+)`, "g");
  formatted = formatted.replace(pattern, (_, elem, digits) => {
    const subDigits = digits
      .split("")
      .map((d: string) => SUB_MAP[d] || d)
      .join("");
    return elem + subDigits;
  });

  // 3. Clean spaces around arrows
  formatted = formatted.replace(/ +→ +/g, " → ").replace(/ +⇌ +/g, " ⇌ ");

  // 4. Normalize ohm symbols and OCR artifacts
  formatted = formatted.replace(/[\u0307\u0323]\s*Ω/g, "Ω");
  formatted = formatted.replace(/[\u2126]/g, "Ω");
  formatted = formatted.replace(/(\d+(?:\.\d+)?)\s*(?:ohms?|Ohms?)\b/g, "$1 Ω");
  formatted = formatted.replace(/(\d+(?:\.\d+)?)\s*Ω/g, "$1 Ω");

  // 5. pi -> π
  formatted = formatted.replace(/\bpi\b/g, "π");

  // 6. Powers and formulas: d^2 -> d², I^2R -> I²R, V^2/R -> V²/R
  formatted = formatted.replace(/\bI\^2\s*R\b/g, "I²R");
  formatted = formatted.replace(/\bV\^2\s*\/\s*R\b/g, "V²/R");
  formatted = formatted.replace(/([a-zA-Z\)])\^([0-9]+)/g, (_, base, digits) => {
    const superDigits = digits
      .split("")
      .map((d: string) => SUB_MAP_SUPER[d] || d)
      .join("");
    return base + superDigits;
  });

  // 7. Multiplication * -> ×
  formatted = formatted.replace(/(?<=[a-zA-Z0-9\)²³⁴⁵⁶⁷⁸⁹⁰π])\s*\*\s*(?=[a-zA-Z0-9\(π])/g, " × ");

  return formatted;
}

export function stripOptionPrefix(optText?: string): string {
  if (!optText) return "";
  let cleaned = String(optText).trim();
  // Strip 'A)', '(A)', 'A.', 'A -', 'Option A:', etc.
  cleaned = cleaned.replace(/^(?:\(?\s*[A-Da-d]\s*[\)\.\:\-]\s*|\bOption\s+\(?[A-Da-d]\)?[\:\.\-]?\s*)/, "");
  return cleaned.trim();
}

export function stripSubQuestionPrefix(stemText?: string): string {
  if (!stemText) return "";
  let cleaned = String(stemText).trim();
  cleaned = cleaned.replace(/^(?:\([iIvVaAbBcCdD0-9]+\)|[iIvVaAbBcCdD0-9]+[\.\)])\s*/, "");
  return cleaned.trim();
}

export function getRomanNumeral(index: number): string {
  if (index >= 0 && index < ROMAN_NUMERALS.length) {
    return ROMAN_NUMERALS[index];
  }
  return `(${index + 1})`;
}

export function cleanStemForSubquestions(stem?: string, subQuestions?: any[]): string {
  if (!stem) return "Answer the following questions:";
  let clean = stem.trim();

  // 1. Match subpart markers like (a), (i), (1), 1., etc.
  const markerMatch = clean.search(/(?:\s*\([a-dA-D1-4ivxIVX]+\)\s+|\s*[1-4]\.\s+)/);
  if (markerMatch !== -1) {
    const leadIn = clean.substring(0, markerMatch).trim();
    if (leadIn.length >= 10) {
      clean = leadIn;
    } else {
      clean = "Answer the following questions:";
    }
  }

  // 2. Check if the text of the first subquestion is embedded in the stem
  if (subQuestions && Array.isArray(subQuestions) && subQuestions.length > 0) {
    const firstSq = subQuestions[0];
    const sqStem = (firstSq?.stem || "").trim();
    if (sqStem.length >= 12 && clean.toLowerCase().includes(sqStem.toLowerCase())) {
      const idx = clean.toLowerCase().indexOf(sqStem.toLowerCase());
      let leadIn = clean.substring(0, idx).trim();
      leadIn = leadIn.replace(/[\(\[]?[a-dA-D1-4ivxIVX]+[\)\]\.]?\s*$/, "").trim();
      if (leadIn.length >= 10) {
        clean = leadIn;
      } else {
        clean = "Answer the following questions:";
      }
    }
  }

  clean = clean.replace(/[\(\[]?[a-dA-D1-4ivxIVX]+[\)\]\.]?\s*$/, "").trim();
  return formatChemicalFormulas(clean);
}
