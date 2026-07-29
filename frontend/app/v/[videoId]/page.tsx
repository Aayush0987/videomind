"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { ApiError, getJob, getVideo } from "@/lib/api";
import { pushRecent } from "@/lib/settings";
import type { JobResponse } from "@/lib/types";
import { ChapterRail, type ChapterRailHandle } from "@/components/ChapterRail";
import { ChatPanel } from "@/components/ChatPanel";
import { EnrichmentPopover } from "@/components/EnrichmentPopover";
import { ProcessingTimeline } from "@/components/ProcessingTimeline";
import { SettingsDrawer } from "@/components/SettingsDrawer";
import {
  VideoPlayer,
  type VideoPlayerHandle,
} from "@/components/VideoPlayer";

function isTerminal(status?: JobResponse["status"]): boolean {
  return status === "ready" || status === "failed";
}

function Workspace() {
  const { videoId } = useParams<{ videoId: string }>();
  const jobId = useSearchParams().get("job");

  const [currentTime, setCurrentTime] = useState(0);
  const [mobileTab, setMobileTab] = useState<"chapters" | "qa">("chapters");
  const [settingsOpen, setSettingsOpen] = useState(false);

  const playerRef = useRef<VideoPlayerHandle>(null);
  const railRef = useRef<ChapterRailHandle>(null);

  // Poll the job until it resolves; stop the moment it's ready or failed (§15).
  const jobQuery = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (q) => (isTerminal(q.state.data?.status) ? false : 1500),
  });

  const jobFailed = jobQuery.data?.status === "failed";
  const jobReady = !jobId || jobQuery.data?.status === "ready";

  const videoQuery = useQuery({
    queryKey: ["video", videoId],
    queryFn: () => getVideo(videoId),
    enabled: jobReady && !jobFailed,
  });

  const video = videoQuery.data;

  useEffect(() => {
    if (video) {
      pushRecent({
        video_id: video.video_id,
        title: video.title,
        thumbnail_url: video.thumbnail_url,
      });
    }
  }, [video]);

  const seek = (seconds: number) => playerRef.current?.seekTo(seconds);
  const cite = (seconds: number) => railRef.current?.pulseAt(seconds);

  // --- Processing / error / loading states ---

  if (jobFailed) {
    return (
      <CenteredNotice
        title="Analysis didn't finish"
        body={
          jobQuery.data?.error_message ??
          "Processing was interrupted. Try again."
        }
      />
    );
  }

  if (!jobReady) {
    return (
      <div className="flex min-h-screen items-center justify-center px-6">
        {jobQuery.data && <ProcessingTimeline job={jobQuery.data} />}
      </div>
    );
  }

  if (videoQuery.isLoading) {
    return <CenteredNotice title="Loading" body="Fetching the analysis…" />;
  }

  if (videoQuery.error) {
    const message =
      videoQuery.error instanceof ApiError
        ? videoQuery.error.message
        : "Couldn't load this video.";
    return <CenteredNotice title="Not available" body={message} />;
  }

  if (!video) return null;

  const player = (
    <VideoPlayer ref={playerRef} videoId={video.video_id} onTime={setCurrentTime} />
  );
  const rail = (
    <ChapterRail
      ref={railRef}
      chapters={video.chapters}
      currentTime={currentTime}
      onSeek={seek}
    />
  );
  const chat = (
    <ChatPanel videoId={video.video_id} chapters={video.chapters} onCite={cite} />
  );

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col px-4 py-4 lg:px-6">
      <header className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <Link
            href="/"
            className="text-xs text-muted hover:text-paper"
          >
            ← New video
          </Link>
          <h1 className="mt-1 truncate font-condensed text-2xl font-bold tracking-tight">
            {video.title}
          </h1>
          <p className="text-sm text-muted">
            {video.channel ? `${video.channel} · ` : ""}
            {video.chapters.length} chapters ·{" "}
            {video.verification.repaired
              ? "chapters auto-corrected"
              : "chapters verified"}
          </p>
        </div>
        <button
          onClick={() => setSettingsOpen(true)}
          className="shrink-0 rounded-md border border-hairline px-3 py-2 text-sm text-muted hover:border-signal hover:text-paper"
        >
          Settings
        </button>
      </header>

      <div className="grid flex-1 grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        {/* Left column: player, enrichments, then the scrollable chapter rail. */}
        <div className="flex min-h-0 flex-col gap-4">
          {player}

          {video.enrichments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {video.enrichments.map((e) => (
                <EnrichmentPopover
                  key={`${e.entity}-${e.first_mention}`}
                  enrichment={e}
                  onSeek={seek}
                />
              ))}
            </div>
          )}

          {/* Desktop: rail always visible. Mobile: tab-gated below. */}
          <div className="hidden min-h-0 flex-1 overflow-y-auto pr-1 scroll-slim lg:block">
            {rail}
          </div>

          {/* Mobile tab switcher (§16.1). */}
          <div className="lg:hidden">
            <div
              role="tablist"
              aria-label="Video panels"
              className="mb-3 flex gap-1 rounded-lg border border-hairline bg-surface p-1"
            >
              <TabButton
                active={mobileTab === "chapters"}
                onClick={() => setMobileTab("chapters")}
              >
                Chapters
              </TabButton>
              <TabButton
                active={mobileTab === "qa"}
                onClick={() => setMobileTab("qa")}
              >
                Q&amp;A
              </TabButton>
            </div>
            {mobileTab === "chapters" ? rail : <div className="h-[70vh]">{chat}</div>}
          </div>
        </div>

        {/* Right column: Q&A, full height on desktop. */}
        <div className="hidden min-h-0 lg:block">{chat}</div>
      </div>

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </main>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex-1 rounded-md px-3 py-2 font-condensed text-sm font-semibold tracking-wide ${
        active ? "bg-signal text-ground" : "text-muted"
      }`}
    >
      {children}
    </button>
  );
}

function CenteredNotice({ title, body }: { title: string; body: string }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-condensed text-2xl font-semibold tracking-wide">
        {title}
      </h1>
      <p className="max-w-md text-muted">{body}</p>
      <Link
        href="/"
        className="mt-2 rounded-md bg-signal px-4 py-2 font-condensed font-semibold tracking-wide text-ground"
      >
        Try another link
      </Link>
    </div>
  );
}

export default function WorkspacePage() {
  return (
    <Suspense fallback={null}>
      <Workspace />
    </Suspense>
  );
}
