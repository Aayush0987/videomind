// Mirrors the backend Pydantic models in app/schemas/api.py (§14, §15).
// Field names are kept snake_case to match the wire format exactly — no
// transformation layer, so what the API sends is what these types describe.

export type Provider = "gemini" | "openai" | "anthropic" | "custom";

export interface LLMConfig {
  provider?: Provider;
  model?: string;
  api_key?: string;
  base_url?: string;
}

export interface ErrorResponse {
  error_code: string;
  message: string;
  detail?: string | null;
}

// --- POST /api/videos ---
export interface AnalyzeResponse {
  cached: boolean;
  video_id: string;
  job_id: string | null;
}

// --- GET /api/jobs/{job_id} ---
export type JobStatus = "queued" | "running" | "ready" | "failed";

export interface JobResponse {
  job_id: string;
  video_id: string | null;
  status: JobStatus;
  stage: string | null;
  stage_label: string | null;
  progress: number;
  retries: Record<string, number>;
  error_code: string | null;
  error_message: string | null;
}

// --- GET /api/videos/{video_id} ---
export interface Chapter {
  chapter_id: string;
  idx: number;
  start: number;
  end: number;
  title: string;
  summary: string;
  key_points: string[];
}

export interface Enrichment {
  entity: string;
  kind: string;
  blurb: string;
  source_url?: string | null;
  first_mention: number;
}

export interface Verification {
  valid: boolean;
  repaired: boolean;
  issues: string[];
}

export interface VideoResponse {
  video_id: string;
  url: string;
  title: string;
  channel?: string | null;
  duration: number;
  thumbnail_url?: string | null;
  transcript_source: string;
  language: string;
  chapters: Chapter[];
  enrichments: Enrichment[];
  verification: Verification;
}

// --- GET /api/videos/{video_id}/transcript ---
export interface TranscriptUnit {
  idx: number;
  start: number;
  end: number;
  text: string;
}

export interface TranscriptResponse {
  units: TranscriptUnit[];
}

// --- POST /api/videos/{video_id}/ask ---
export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface AskRequest {
  question: string;
  history: ChatTurn[];
  llm?: LLMConfig;
}

export interface Citation {
  marker: string;
  chunk_id: string;
  start: number;
  end: number;
  quote: string;
  chapter_title: string;
}

export interface Trace {
  strategy: string;
  retrieval_attempts: number;
  chunks_retrieved: number;
  chunks_kept: number;
  dropped_citations: number;
  nodes: string[];
  latency_ms: number;
}

export type Confidence = "high" | "medium" | "low";

export interface AskResponse {
  answer: string;
  citations: Citation[];
  confidence: Confidence;
  trace: Trace;
}

// --- POST /api/llm/ping ---
export interface PingResponse {
  ok: boolean;
  error?: string | null;
}

// --- GET /api/health ---
export interface HealthResponse {
  status: string;
  version: string;
  embedder: string;
  embedding_dim: number;
  collection: string;
  whisper_enabled: boolean;
  videos_cached: number;
}
