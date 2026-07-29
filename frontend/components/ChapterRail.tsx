"use client";

import {
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChapterCard } from "./ChapterCard";
import type { Chapter } from "@/lib/types";

// The rail is a to-scale map of the video: every block's height is proportional
// to its real duration, so the spine down the left edge *is* the timeline
// (§16.2). A floor keeps very short chapters legible without breaking the map.
const PX_PER_SECOND = 0.9;
const MIN_BLOCK_PX = 96;

export interface ChapterRailHandle {
  // Pulse a citation's position on the spine, then seek there (§16.2).
  pulseAt: (seconds: number) => void;
}

function activeIndex(chapters: Chapter[], t: number): number {
  for (let i = chapters.length - 1; i >= 0; i--) {
    if (t >= chapters[i].start) return i;
  }
  return 0;
}

export const ChapterRail = forwardRef<
  ChapterRailHandle,
  {
    chapters: Chapter[];
    currentTime: number;
    onSeek: (seconds: number) => void;
  }
>(function ChapterRail({ chapters, currentTime, onSeek }, ref) {
  const cardRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const [pulse, setPulse] = useState<{ y: number; key: number } | null>(null);

  // Per-block heights and their cumulative offsets down the spine.
  const { heights, offsets, total } = useMemo(() => {
    const heights = chapters.map((c) =>
      Math.max(MIN_BLOCK_PX, (c.end - c.start) * PX_PER_SECOND),
    );
    const offsets: number[] = [];
    let running = 0;
    for (const h of heights) {
      offsets.push(running);
      running += h;
    }
    return { heights, offsets, total: running };
  }, [chapters]);

  // Map a video timestamp to a vertical pixel position on the spine.
  const yFor = (t: number): number => {
    const i = activeIndex(chapters, t);
    const ch = chapters[i];
    const span = Math.max(1, ch.end - ch.start);
    const frac = Math.min(1, Math.max(0, (t - ch.start) / span));
    return offsets[i] + frac * heights[i];
  };

  const active = activeIndex(chapters, currentTime);
  const playheadY = yFor(currentTime);

  useImperativeHandle(
    ref,
    () => ({
      pulseAt: (seconds: number) => {
        const reduce =
          typeof window !== "undefined" &&
          window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
        if (reduce) {
          onSeek(seconds);
          return;
        }
        setPulse({ y: yFor(seconds), key: Date.now() });
        window.setTimeout(() => {
          onSeek(seconds);
          setPulse(null);
        }, 450);
      },
    }),
    // yFor closes over current layout; recompute the handle when it changes.
    [chapters, heights, offsets],
  );

  // Arrow keys move focus between chapter blocks (§16.2 quality floor).
  const onKeyDown = (e: React.KeyboardEvent, i: number) => {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      const next = e.key === "ArrowDown" ? i + 1 : i - 1;
      cardRefs.current[next]?.focus();
    }
  };

  return (
    <div className="flex gap-3">
      {/* The spine: a continuous vertical line with a node per chapter and a
          cyan playhead that travels down it as the video plays. */}
      <div className="relative w-4 shrink-0" style={{ height: total }} aria-hidden>
        <span className="absolute left-1/2 top-0 h-full w-px -translate-x-1/2 bg-hairline" />
        <span
          className="absolute left-1/2 top-0 w-px -translate-x-1/2 bg-signal transition-[height] duration-300 ease-linear"
          style={{ height: playheadY }}
        />
        {chapters.map((c, i) => (
          <span
            key={c.chapter_id}
            className={`absolute left-1/2 h-2 w-2 -translate-x-1/2 rounded-full ${
              i <= active ? "bg-signal" : "bg-hairline"
            }`}
            style={{ top: offsets[i] }}
          />
        ))}
        {/* Playhead marker. */}
        <span
          className="absolute left-1/2 h-3 w-3 -translate-x-1/2 rounded-full border-2 border-ground bg-signal shadow-[0_0_8px_#38E1D4] transition-[top] duration-300 ease-linear"
          style={{ top: playheadY - 6 }}
        />
        {/* Amber citation pulse, shown briefly before seeking. */}
        {pulse && (
          <span
            key={pulse.key}
            className="absolute left-1/2 h-3 w-3 -translate-x-1/2 animate-citation-pulse rounded-full bg-citation"
            style={{ top: pulse.y - 6 }}
          />
        )}
      </div>

      <ol className="flex flex-1 flex-col gap-2" aria-label="Chapters">
        {chapters.map((c, i) => (
          <li
            key={c.chapter_id}
            className="animate-rail-assemble"
            style={{ animationDelay: `${i * 60}ms` }}
            onKeyDown={(e) => onKeyDown(e, i)}
          >
            <ChapterCard
              ref={(el) => {
                cardRefs.current[i] = el;
              }}
              chapter={c}
              active={i === active}
              height={heights[i]}
              onSeek={onSeek}
            />
          </li>
        ))}
      </ol>
    </div>
  );
});
