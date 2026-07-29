// Pure display helpers shared across components. Kept dependency-free so they
// can be unit-tested in isolation (§18.3: timecode formatting, marker→chip).

import type { Citation } from "./types";

// Timecodes are always mm:ss, and only grow to h:mm:ss past 60 minutes (§16.2).
export function formatTimecode(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const s = total % 60;
  const m = Math.floor(total / 60) % 60;
  const h = Math.floor(total / 3600);
  const pad = (n: number) => n.toString().padStart(2, "0");
  if (h > 0) return `${h}:${pad(m)}:${pad(s)}`;
  return `${pad(m)}:${pad(s)}`;
}

// An answer segment is either plain prose or a resolved citation marker. The
// backend emits markers as `[[c0]]`; we split the answer into a flat sequence
// so ChatPanel can render prose as text and markers as clickable CitationChips.
export type AnswerSegment =
  | { kind: "text"; text: string }
  | { kind: "citation"; marker: string; citation: Citation | null };

const MARKER_RE = /\[\[(c\d+)\]\]/g;

export function parseAnswer(
  answer: string,
  citations: Citation[],
): AnswerSegment[] {
  const byMarker = new Map(citations.map((c) => [c.marker, c]));
  const segments: AnswerSegment[] = [];
  let cursor = 0;
  for (const match of answer.matchAll(MARKER_RE)) {
    const idx = match.index ?? 0;
    if (idx > cursor) {
      segments.push({ kind: "text", text: answer.slice(cursor, idx) });
    }
    const marker = match[1];
    segments.push({
      kind: "citation",
      marker,
      citation: byMarker.get(marker) ?? null,
    });
    cursor = idx + match[0].length;
  }
  if (cursor < answer.length) {
    segments.push({ kind: "text", text: answer.slice(cursor) });
  }
  return segments;
}
