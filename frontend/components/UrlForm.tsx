"use client";

import { useState } from "react";

export function UrlForm({
  onSubmit,
  pending,
  error,
}: {
  onSubmit: (url: string) => void;
  pending: boolean;
  error: string | null;
}) {
  const [url, setUrl] = useState("");

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = url.trim();
    if (trimmed) onSubmit(trimmed);
  };

  return (
    <form onSubmit={submit} className="flex w-full flex-col gap-3">
      <label htmlFor="video-url" className="sr-only">
        YouTube video URL
      </label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <input
          id="video-url"
          type="url"
          inputMode="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="Paste a YouTube link"
          autoFocus
          className="flex-1 rounded-lg border border-hairline bg-surface px-4 py-3 text-lg text-paper placeholder:text-muted focus:border-signal"
        />
        <button
          type="submit"
          disabled={pending || !url.trim()}
          className="rounded-lg bg-signal px-6 py-3 font-condensed text-lg font-semibold tracking-wide text-ground transition hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {pending ? "Analyzing…" : "Analyze video"}
        </button>
      </div>
      {error && (
        <p role="alert" className="text-sm text-citation">
          {error}
        </p>
      )}
    </form>
  );
}
