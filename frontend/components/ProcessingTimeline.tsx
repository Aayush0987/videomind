"use client";

import type { JobResponse } from "@/lib/types";

// Mirrors STAGE_WEIGHTS / STAGE_LABELS in backend app/config.py (§10.3, §16.4).
// The frontend can't import backend Python, so the ordered stage list lives
// here; the job poll drives which one is active.
const STAGES: { name: string; label: string }[] = [
  { name: "resolve_source", label: "Resolving video" },
  { name: "fetch_transcript", label: "Fetching transcript" },
  { name: "normalize", label: "Normalizing transcript" },
  { name: "propose_boundaries", label: "Detecting chapter boundaries" },
  { name: "verify_repair", label: "Verifying chapters" },
  { name: "title_and_summarize", label: "Writing chapter summaries" },
  { name: "entities", label: "Extracting key entities" },
  { name: "enrich", label: "Adding background notes" },
  { name: "index", label: "Indexing for search" },
];

type StageState = "pending" | "active" | "done";

function stateFor(
  stageIndex: number,
  currentIndex: number,
  status: JobResponse["status"],
): StageState {
  if (status === "ready") return "done";
  if (stageIndex < currentIndex) return "done";
  if (stageIndex === currentIndex) return "active";
  return "pending";
}

function Dot({ state }: { state: StageState }) {
  if (state === "done") {
    return (
      <span className="grid h-5 w-5 place-items-center rounded-full bg-signal text-ground">
        <svg viewBox="0 0 12 12" className="h-3 w-3" aria-hidden>
          <path
            d="M2.5 6.5l2.2 2.2L9.5 3.8"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }
  if (state === "active") {
    return (
      <span className="relative grid h-5 w-5 place-items-center">
        <span className="absolute h-5 w-5 animate-ping rounded-full bg-signal/40" />
        <span className="h-2.5 w-2.5 rounded-full bg-signal" />
      </span>
    );
  }
  return <span className="h-5 w-5 rounded-full border border-hairline" />;
}

export function ProcessingTimeline({ job }: { job: JobResponse }) {
  const currentIndex = Math.max(
    0,
    STAGES.findIndex((s) => s.name === job.stage),
  );
  const segRetries = job.retries?.segmentation ?? 0;
  const pct = Math.round(job.progress * 100);

  return (
    <section
      aria-label="Processing progress"
      className="mx-auto flex w-full max-w-md flex-col gap-1"
    >
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="font-condensed text-lg font-semibold tracking-wide">
          Analyzing
        </h2>
        <span className="tabular font-condensed text-sm text-muted">{pct}%</span>
      </div>

      <ol className="relative flex flex-col">
        {STAGES.map((stage, i) => {
          const state = stateFor(i, currentIndex, job.status);
          const showRetry = stage.name === "propose_boundaries" && segRetries > 0;
          return (
            <li key={stage.name} className="flex gap-3">
              <div className="flex flex-col items-center">
                <Dot state={state} />
                {i < STAGES.length - 1 && (
                  <span
                    className={`w-px flex-1 ${
                      state === "done" ? "bg-signal/50" : "bg-hairline"
                    }`}
                    style={{ minHeight: showRetry ? 44 : 24 }}
                  />
                )}
              </div>
              <div className="pb-4">
                <p
                  className={`text-sm ${
                    state === "pending" ? "text-muted" : "text-paper"
                  } ${state === "active" ? "animate-stage-in" : ""}`}
                >
                  {stage.label}
                </p>
                {/* The retry is the most interesting thing the system does —
                    surface it, never hide it (§16.4). */}
                {showRetry && (
                  <p className="mt-1 text-xs text-citation">
                    Chapters failed validation — re-segmenting
                    {segRetries > 1 ? ` (attempt ${segRetries + 1})` : ""}.
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
