"use client";

import { useState } from "react";
import type { Trace } from "@/lib/types";

// The collapsible reasoning panel under each answer (§16.5). It renders the
// node path as chips, the strategy, retrieved-vs-kept counts, and any dropped
// citations — this is the system showing its work and where it self-corrected.
export function AgentTrace({ trace }: { trace: Trace }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1.5 text-xs text-muted hover:text-paper"
      >
        <span className={`transition-transform ${open ? "rotate-90" : ""}`}>
          ▸
        </span>
        How this answer was built · {trace.strategy} ·{" "}
        <span className="tabular">{trace.latency_ms} ms</span>
      </button>

      {open && (
        <div className="mt-2 rounded-lg border border-hairline bg-ground/60 p-3">
          <div className="flex flex-wrap items-center gap-1.5">
            {trace.nodes.map((node, i) => (
              <span key={i} className="flex items-center gap-1.5">
                <code className="rounded bg-surface px-1.5 py-0.5 font-condensed text-xs tracking-wide text-paper/90">
                  {node}
                </code>
                {i < trace.nodes.length - 1 && (
                  <span className="text-muted">→</span>
                )}
              </span>
            ))}
          </div>

          <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs sm:grid-cols-4">
            <Stat label="Strategy" value={trace.strategy} />
            <Stat label="Retrieval passes" value={trace.retrieval_attempts} />
            <Stat label="Chunks retrieved" value={trace.chunks_retrieved} />
            <Stat label="Chunks kept" value={trace.chunks_kept} />
          </dl>

          {trace.dropped_citations > 0 && (
            <p className="mt-3 text-xs text-citation">
              {trace.dropped_citations} citation
              {trace.dropped_citations === 1 ? "" : "s"} dropped in validation —
              markers renumbered.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="flex flex-col">
      <dt className="text-muted">{label}</dt>
      <dd className="tabular font-condensed text-paper">{value}</dd>
    </div>
  );
}
