"use client";

import { useMutation } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { analyzeVideo, ApiError } from "@/lib/api";
import { loadRecent, type RecentVideo } from "@/lib/settings";
import { SettingsDrawer } from "@/components/SettingsDrawer";
import { UrlForm } from "@/components/UrlForm";

export default function LandingPage() {
  const router = useRouter();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [recent, setRecent] = useState<RecentVideo[]>([]);

  useEffect(() => {
    setRecent(loadRecent());
  }, []);

  const analyze = useMutation({
    mutationFn: (url: string) => analyzeVideo(url),
    onSuccess: (res) => {
      const suffix = res.job_id ? `?job=${res.job_id}` : "";
      router.push(`/v/${res.video_id}${suffix}`);
    },
  });

  const error =
    analyze.error instanceof ApiError
      ? analyze.error.message
      : analyze.error
        ? "Couldn't start analysis. Check the link and try again."
        : null;

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-10 px-6 py-16">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="font-condensed text-5xl font-bold tracking-tight text-paper">
            VideoMind
          </h1>
          <p className="mt-2 max-w-md text-muted">
            Paste a YouTube link. Get topic chapters and grounded answers with
            clickable timestamp citations.
          </p>
        </div>
        <button
          onClick={() => setSettingsOpen(true)}
          className="rounded-md border border-hairline px-3 py-2 text-sm text-muted hover:border-signal hover:text-paper"
        >
          Settings
        </button>
      </div>

      <UrlForm
        onSubmit={(url) => analyze.mutate(url)}
        pending={analyze.isPending}
        error={error}
      />

      {recent.length > 0 && (
        <section>
          <h2 className="mb-3 font-condensed text-sm font-semibold uppercase tracking-widest text-muted">
            Recent videos
          </h2>
          <ul className="flex flex-col divide-y divide-hairline overflow-hidden rounded-lg border border-hairline">
            {recent.map((v) => (
              <li key={v.video_id}>
                <button
                  onClick={() => router.push(`/v/${v.video_id}`)}
                  className="flex w-full items-center gap-3 bg-surface px-3 py-2.5 text-left hover:bg-hairline/40"
                >
                  {v.thumbnail_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={v.thumbnail_url}
                      alt=""
                      className="h-10 w-16 rounded object-cover"
                    />
                  ) : (
                    <span className="h-10 w-16 rounded bg-hairline" />
                  )}
                  <span className="line-clamp-2 text-sm text-paper">
                    {v.title}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <SettingsDrawer open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </main>
  );
}
