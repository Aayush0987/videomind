// localStorage-backed LLM config (§16.7) and the recent-videos list (§16.1).
// The key is *only* ever sent with a request; it is never persisted anywhere
// but the user's own browser storage, and never logged.

import type { LLMConfig, Provider } from "./types";

const LLM_KEY = "videomind.llm";
const RECENT_KEY = "videomind.recent";
const RECENT_LIMIT = 8;

const PROVIDERS: Provider[] = ["gemini", "openai", "anthropic", "custom"];

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

// --- LLM config ----------------------------------------------------------

// Exported for unit testing without touching the DOM (§18.3).
export function serializeLLMConfig(config: LLMConfig): string {
  return JSON.stringify(config);
}

export function deserializeLLMConfig(raw: string | null): LLMConfig {
  if (!raw) return {};
  const parsed = JSON.parse(raw) as Partial<LLMConfig>;
  const config: LLMConfig = {};
  if (parsed.provider && PROVIDERS.includes(parsed.provider)) {
    config.provider = parsed.provider;
  }
  if (typeof parsed.model === "string" && parsed.model.trim()) {
    config.model = parsed.model.trim();
  }
  if (typeof parsed.api_key === "string" && parsed.api_key) {
    config.api_key = parsed.api_key;
  }
  if (typeof parsed.base_url === "string" && parsed.base_url.trim()) {
    config.base_url = parsed.base_url.trim();
  }
  return config;
}

export function loadLLMConfig(): LLMConfig {
  if (!isBrowser()) return {};
  try {
    return deserializeLLMConfig(window.localStorage.getItem(LLM_KEY));
  } catch {
    return {};
  }
}

export function saveLLMConfig(config: LLMConfig): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(LLM_KEY, serializeLLMConfig(config));
}

// The API treats an all-empty config the same as "use server defaults", so we
// only attach it to a request when the user actually set something.
export function hasLLMConfig(config: LLMConfig): boolean {
  return Boolean(
    config.provider || config.model || config.api_key || config.base_url,
  );
}

// --- Recent videos -------------------------------------------------------

export interface RecentVideo {
  video_id: string;
  title: string;
  thumbnail_url?: string | null;
  at: number;
}

export function loadRecent(): RecentVideo[] {
  if (!isBrowser()) return [];
  try {
    const raw = window.localStorage.getItem(RECENT_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as RecentVideo[];
  } catch {
    return [];
  }
}

export function pushRecent(video: Omit<RecentVideo, "at">): void {
  if (!isBrowser()) return;
  const existing = loadRecent().filter((v) => v.video_id !== video.video_id);
  const next = [{ ...video, at: Date.now() }, ...existing].slice(0, RECENT_LIMIT);
  window.localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}
