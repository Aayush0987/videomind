"use client";

import { formatTimecode } from "@/lib/format";
import type { Citation } from "@/lib/types";

// The amber marker inside an answer. Amber means citation, and only citation.
// Clicking pulses on the spine, then seeks (the parent wires onSeek to the
// rail's pulseAt). If a marker was dropped in validation it has no citation and
// renders as inert amber text.
export function CitationChip({
  marker,
  citation,
  onSeek,
}: {
  marker: string;
  citation: Citation | null;
  onSeek: (seconds: number) => void;
}) {
  if (!citation) {
    return <sup className="px-0.5 text-xs text-citation/70">[{marker}]</sup>;
  }

  return (
    <button
      onClick={() => onSeek(citation.start)}
      title={`${citation.chapter_title} — “${citation.quote}”`}
      aria-label={`Citation at ${formatTimecode(citation.start)} in ${citation.chapter_title}`}
      className="mx-0.5 inline-flex items-baseline gap-1 rounded border border-citation/40 bg-citation/10 px-1.5 py-0.5 align-baseline text-xs text-citation transition-colors hover:bg-citation/20"
    >
      <span className="tabular font-condensed">
        {formatTimecode(citation.start)}
      </span>
    </button>
  );
}
