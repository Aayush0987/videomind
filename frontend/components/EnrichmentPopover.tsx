"use client";

import { useState } from "react";
import { formatTimecode } from "@/lib/format";
import type { Enrichment } from "@/lib/types";

// A single background-note entity: a chip that reveals a blurb, a source link,
// and a jump to where the entity is first mentioned.
export function EnrichmentPopover({
  enrichment,
  onSeek,
}: {
  enrichment: Enrichment;
  onSeek: (seconds: number) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative inline-block">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="rounded-full border border-hairline bg-surface px-3 py-1 font-condensed text-sm tracking-wide text-paper hover:border-signal"
      >
        {enrichment.entity}
        <span className="ml-1.5 text-xs text-muted">{enrichment.kind}</span>
      </button>

      {open && (
        <>
          <button
            aria-label="Dismiss note"
            className="fixed inset-0 z-10 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div className="absolute left-0 top-full z-20 mt-2 w-72 rounded-lg border border-hairline bg-surface p-4 shadow-xl">
            <p className="font-condensed text-base font-semibold tracking-wide">
              {enrichment.entity}
            </p>
            <p className="mt-1.5 text-sm leading-relaxed text-paper/90">
              {enrichment.blurb}
            </p>
            <div className="mt-3 flex items-center justify-between text-sm">
              <button
                onClick={() => {
                  onSeek(enrichment.first_mention);
                  setOpen(false);
                }}
                className="tabular font-condensed text-signal hover:underline"
              >
                Jump to {formatTimecode(enrichment.first_mention)}
              </button>
              {enrichment.source_url && (
                <a
                  href={enrichment.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-muted hover:text-paper"
                >
                  Source ↗
                </a>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
