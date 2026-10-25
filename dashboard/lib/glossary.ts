import type { GlossaryEntry } from "./api/types";

/**
 * Dari typed on an Arabic keyboard (ي, ك) reads as the Persian letters, and the
 * zero-width non-joiner as a space, so "دوسیه ها" finds "دوسیه‌ها".
 */
const PERSIAN_FOLD: Record<string, string> = { "ي": "ی", "ى": "ی", "ك": "ک", "‌": " " };

/** Lowercase without accents, one UTF-16 unit per unit in, so indexes line up. */
function fold(text: string): string {
  let out = "";
  for (let i = 0; i < text.length; i++) {
    const persian = PERSIAN_FOLD[text[i]];
    if (persian) {
      out += persian;
      continue;
    }
    const c = text[i].normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    out += c[0] ?? text[i];
  }
  return out;
}

const WORD = /[\p{L}\p{N}]/u;

export interface Segment {
  text: string;
  entry: GlossaryEntry | null;
}

/**
 * Splits `text` around the glossary terms it uses, longest terms first, so
 * "entrevista de asilo" wins over "asilo". Matching ignores case and accents and
 * allows a plural ending, like the translator's grounding (translation/glossary.py).
 * `side` picks which column to look for: the translation, or the English term.
 */
export function findTerms(text: string, entries: GlossaryEntry[], side: "translation" | "term"): Segment[] {
  const hay = fold(text);
  const taken: { start: number; end: number; entry: GlossaryEntry }[] = [];
  const sorted = [...entries].sort((a, b) => b[side].length - a[side].length);
  for (const entry of sorted) {
    const needle = fold(entry[side]);
    if (!needle) continue;
    for (let from = 0; ; ) {
      const start = hay.indexOf(needle, from);
      if (start < 0) break;
      let end = start + needle.length;
      if (hay.startsWith("es", end) && !WORD.test(hay[end + 2] ?? "")) end += 2;
      else if (hay[end] === "s" && !WORD.test(hay[end + 1] ?? "")) end += 1;
      const bounded = !WORD.test(hay[start - 1] ?? "") && !WORD.test(hay[end] ?? "");
      if (bounded && !taken.some((t) => start < t.end && end > t.start)) taken.push({ start, end, entry });
      from = start + 1;
    }
  }
  taken.sort((a, b) => a.start - b.start);
  const segments: Segment[] = [];
  let at = 0;
  for (const t of taken) {
    if (t.start > at) segments.push({ text: text.slice(at, t.start), entry: null });
    segments.push({ text: text.slice(t.start, t.end), entry: t.entry });
    at = t.end;
  }
  if (at < text.length) segments.push({ text: text.slice(at), entry: null });
  return segments;
}

/**
 * Entries with a word in the term or translation that starts with `query`, so
 * "cita" finds "notificación de cita" but not "solicitante". Whole-entry prefix
 * matches first.
 */
export function searchGlossary(entries: GlossaryEntry[], query: string): GlossaryEntry[] {
  const q = fold(query.trim());
  if (!q) return [];
  const atWord = (s: string) => {
    for (let i = s.indexOf(q); i >= 0; i = s.indexOf(q, i + 1)) {
      if (!WORD.test(s[i - 1] ?? "")) return true;
    }
    return false;
  };
  const hits = entries.filter((e) => atWord(fold(e.term)) || atWord(fold(e.translation)));
  const starts = (e: GlossaryEntry) => fold(e.term).startsWith(q) || fold(e.translation).startsWith(q);
  return hits.sort((a, b) => Number(starts(b)) - Number(starts(a)));
}
