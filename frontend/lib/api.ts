// Typed fetch client — the frontend's only door to the backend (§14).
// Every request that can use a user-supplied model attaches the localStorage
// LLM config; the key rides along per-request and is never stored server-side.

import { hasLLMConfig, loadLLMConfig } from "./settings";
import type {
  AnalyzeResponse,
  AskResponse,
  ChatTurn,
  ErrorResponse,
  HealthResponse,
  JobResponse,
  LLMConfig,
  PingResponse,
  TranscriptResponse,
  VideoResponse,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ??
  "http://localhost:8000";

// A thrown ApiError carries the backend's error envelope so the UI can show a
// safe, specific message and branch on the machine-readable code (§14.1).
export class ApiError extends Error {
  code: string;
  detail?: string | null;
  status: number;

  constructor(status: number, body: ErrorResponse) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.error_code;
    this.detail = body.detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, {
      error_code: "llm_unavailable",
      message: "Couldn't reach VideoMind. Check the backend is running.",
    });
  }
  if (resp.status === 204) return undefined as T;
  const body = await resp.json();
  if (!resp.ok) {
    throw new ApiError(resp.status, body as ErrorResponse);
  }
  return body as T;
}

function withLLM<T extends object>(payload: T): T & { llm?: LLMConfig } {
  const config = loadLLMConfig();
  return hasLLMConfig(config) ? { ...payload, llm: config } : payload;
}

// --- Endpoints (§14.2) ---------------------------------------------------

export function analyzeVideo(
  url: string,
  forceRefresh = false,
): Promise<AnalyzeResponse> {
  return request<AnalyzeResponse>("/videos", {
    method: "POST",
    body: JSON.stringify(withLLM({ url, force_refresh: forceRefresh })),
  });
}

export function getJob(jobId: string): Promise<JobResponse> {
  return request<JobResponse>(`/jobs/${jobId}`);
}

export function getVideo(videoId: string): Promise<VideoResponse> {
  return request<VideoResponse>(`/videos/${videoId}`);
}

export function getTranscript(videoId: string): Promise<TranscriptResponse> {
  return request<TranscriptResponse>(`/videos/${videoId}/transcript`);
}

export function askQuestion(
  videoId: string,
  question: string,
  history: ChatTurn[],
): Promise<AskResponse> {
  return request<AskResponse>(`/videos/${videoId}/ask`, {
    method: "POST",
    body: JSON.stringify(withLLM({ question, history })),
  });
}

export function deleteVideo(videoId: string): Promise<void> {
  return request<void>(`/videos/${videoId}`, { method: "DELETE" });
}

// The Settings drawer's "Test connection" button — one 5-token generate (§16.7).
export function pingLLM(config: LLMConfig): Promise<PingResponse> {
  return request<PingResponse>("/llm/ping", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/health");
}
