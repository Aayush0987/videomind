"use client";

import { forwardRef } from "react";
import { formatTimecode } from "@/lib/format";
import type { Chapter } from "@/lib/types";

// One chapter block in the rail. Sized by the rail (proportional to duration);
// this component only renders content and the active state.
export const ChapterCard = forwardRef<
  HTMLButtonElement,
  {
    chapter: Chapter;
    active: boolean;
    height: number;
    onSeek: (seconds: number) => void;
  }
>(function ChapterCard({ chapter, active, height, onSeek }, ref) {
  return (
    <button
      ref={ref}
      onClick={() => onSeek(chapter.start)}
      aria-current={active ? "true" : undefined}
      style={{ minHeight: height }}
      className={`group flex w-full flex-col gap-1.5 rounded-lg border px-4 py-3 text-left transition-colors ${
        active
          ? "border-signal bg-signal/5"
          : "border-hairline bg-surface hover:border-muted"
      }`}
    >
      <div className="flex items-baseline gap-2">
        <span
          className={`tabular font-condensed text-sm ${
            active ? "text-signal" : "text-muted"
          }`}
        >
          {formatTimecode(chapter.start)}
        </span>
        <h3
          className={`font-condensed text-base font-semibold leading-tight tracking-wide ${
            active ? "text-paper" : "text-paper/90"
          }`}
        >
          {chapter.title}
        </h3>
      </div>
      <p className="text-sm leading-relaxed text-muted">{chapter.summary}</p>
      {chapter.key_points.length > 0 && (
        <ul className="mt-1 flex flex-col gap-1">
          {chapter.key_points.map((point, i) => (
            <li key={i} className="flex gap-2 text-sm text-paper/80">
              <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-muted" />
              <span className="leading-relaxed">{point}</span>
            </li>
          ))}
        </ul>
      )}
    </button>
  );
});
