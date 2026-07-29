"use client";

import { useEffect, useState } from "react";
import { pingLLM } from "@/lib/api";
import { loadLLMConfig, saveLLMConfig } from "@/lib/settings";
import type { LLMConfig, Provider } from "@/lib/types";

const PROVIDERS: { value: Provider; label: string }[] = [
  { value: "gemini", label: "Gemini" },
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "custom", label: "Custom (OpenAI-compatible)" },
];

type PingState =
  | { kind: "idle" }
  | { kind: "testing" }
  | { kind: "ok" }
  | { kind: "error"; message: string };

export function SettingsDrawer({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [config, setConfig] = useState<LLMConfig>({});
  const [ping, setPing] = useState<PingState>({ kind: "idle" });

  // Re-hydrate from storage each time the drawer opens, so it reflects reality.
  useEffect(() => {
    if (open) {
      setConfig(loadLLMConfig());
      setPing({ kind: "idle" });
    }
  }, [open]);

  // Escape closes the drawer — keyboard parity with the backdrop click.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const update = (patch: Partial<LLMConfig>) =>
    setConfig((prev) => ({ ...prev, ...patch }));

  const provider = config.provider ?? "gemini";
  const showBaseUrl = provider === "custom";

  const save = () => {
    saveLLMConfig(config);
    onClose();
  };

  const test = async () => {
    setPing({ kind: "testing" });
    try {
      const res = await pingLLM(config);
      setPing(
        res.ok
          ? { kind: "ok" }
          : { kind: "error", message: res.error ?? "Connection failed." },
      );
    } catch {
      setPing({ kind: "error", message: "Couldn't reach the backend." });
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="LLM settings">
      <button
        aria-label="Close settings"
        className="absolute inset-0 bg-black/60"
        onClick={onClose}
      />
      <aside className="relative flex h-full w-full max-w-md flex-col gap-6 overflow-y-auto border-l border-hairline bg-surface p-6 scroll-slim">
        <header className="flex items-center justify-between">
          <h2 className="font-condensed text-xl font-semibold tracking-wide">
            Model settings
          </h2>
          <button
            onClick={onClose}
            className="rounded px-2 py-1 text-muted hover:text-paper"
            aria-label="Close settings"
          >
            Close
          </button>
        </header>

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">Provider</span>
          <select
            value={provider}
            onChange={(e) => update({ provider: e.target.value as Provider })}
            className="rounded-md border border-hairline bg-ground px-3 py-2 text-paper"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">Model</span>
          <input
            type="text"
            value={config.model ?? ""}
            onChange={(e) => update({ model: e.target.value })}
            placeholder="gemini-2.5-flash"
            className="rounded-md border border-hairline bg-ground px-3 py-2 font-condensed text-paper placeholder:text-muted"
          />
        </label>

        <label className="flex flex-col gap-1.5 text-sm">
          <span className="text-muted">API key</span>
          <input
            type="password"
            value={config.api_key ?? ""}
            onChange={(e) => update({ api_key: e.target.value })}
            placeholder="Paste your key"
            autoComplete="off"
            className="rounded-md border border-hairline bg-ground px-3 py-2 text-paper placeholder:text-muted"
          />
          <span className="text-xs leading-relaxed text-muted">
            Your key is sent with each request and used only for that request. It
            is never stored on the server.
          </span>
        </label>

        {showBaseUrl && (
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-muted">Base URL</span>
            <input
              type="text"
              value={config.base_url ?? ""}
              onChange={(e) => update({ base_url: e.target.value })}
              placeholder="https://your-endpoint/v1"
              className="rounded-md border border-hairline bg-ground px-3 py-2 text-paper placeholder:text-muted"
            />
          </label>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={test}
            disabled={ping.kind === "testing"}
            className="rounded-md border border-hairline px-3 py-2 text-sm text-paper hover:border-signal disabled:opacity-60"
          >
            {ping.kind === "testing" ? "Testing…" : "Test connection"}
          </button>
          {ping.kind === "ok" && (
            <span className="text-sm text-signal">Connected.</span>
          )}
          {ping.kind === "error" && (
            <span className="text-sm text-citation">{ping.message}</span>
          )}
        </div>

        <button
          onClick={save}
          className="mt-auto rounded-md bg-signal px-4 py-2.5 font-condensed font-semibold tracking-wide text-ground hover:brightness-105"
        >
          Save settings
        </button>
      </aside>
    </div>
  );
}
