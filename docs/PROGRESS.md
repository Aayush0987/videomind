# VideoMind — Project Progress

Status as of Phase 4 completion. The project follows a 10-phase build
order defined in the [implementation plan](VIDEOMIND_IMPLEMENTATION_PLAN.md) §22.

---

## Completed Phases

### Phase 0 — Scaffold (`5caeb63`)

Monorepo layout with all directories, empty module stubs, and tooling:

- `pyproject.toml` with pinned dependencies, ruff config, pytest config
- `docker-compose.yml`, `Makefile` (dev, test, lint, mlflow targets)
- CI workflows (lint + test)
- `docs/DECISIONS.md` seeded with three architecture decisions
- One smoke test asserting `Settings()` loads cleanly

### Phase 1 — LLM adapter + rate limiter + fakes (`c6c8990`)

The provider-agnostic LLM layer that everything downstream calls through:

- **`core/llm.py`** — `generate()` and `generate_structured()` with
  automatic retry (429/500), structured JSON output with one repair
  attempt, markdown fence stripping. Supports Gemini, OpenAI, Anthropic,
  and any OpenAI-compatible custom endpoint via `LLMConfig`.
- **`core/ratelimit.py`** — Token-bucket rate limiter with per-minute and
  per-day quotas, async `acquire()`, fake-clock support for testing.
- **`core/errors.py`** — Typed domain errors (`LLMAuthError`,
  `LLMUnavailableError`, `StructuredOutputError`, `DailyQuotaExhausted`).
- **`tests/fakes/fake_llm.py`** — `FakeLLM` with canned responses dict,
  call log, and failure injection (`fail_next`, `return_invalid_json_next`).
- **Import boundary enforced**: only `core/llm.py` may import `litellm`
  (ruff rule + test).

**Tests**: 38 tests covering provider mapping, structured parse, retry
logic, rate limiting with fake clock, error typing.

### Phase 2 — Ingestion + normalization + cache (`509e87d`)

YouTube video ingestion and transcript processing:

- **`ingestion/youtube.py`** — URL parsing (12 URL patterns), metadata
  fetching via YouTube Data API with yt-dlp fallback, video duration
  validation.
- **`ingestion/captions.py`** — Four-rung transcript acquisition ladder:
  YouTube API captions → yt-dlp auto-captions → yt-dlp manual captions →
  Whisper fallback.
- **`ingestion/normalize.py`** — Raw cues → `SentenceUnit` atoms.
  Handles punctuated and unpunctuated transcripts, merges overlapping
  cues, strips `[Music]`/`[Applause]` tags, enforces contiguity and
  max duration/char constraints.
- **`core/db.py`** — SQLite schema with `videos` and `transcripts`
  tables, cache-hit detection, analysis versioning.
- **`scripts/ingest_cli.py`** — CLI for manual transcript ingestion and
  cache inspection.
- **Test fixtures**: real 45-minute auto-caption transcript (unpunctuated,
  the hard case) and a short punctuated transcript.

**Tests**: 32 tests covering URL parsing (12 patterns + invalid), ISO-8601
duration parsing, normalization on both fixtures, cue deduplication,
music stripping, unit contiguity.

### Phase 3 — Embeddings, chunking, vector store, retrieval (`31ac249`)

The embedding and retrieval infrastructure:

- **`core/embedder.py`** — `Embedder` protocol with async
  `embed_passages` / `embed_query` (asymmetric: `RETRIEVAL_DOCUMENT` vs
  `RETRIEVAL_QUERY` task types). `GeminiEmbedder` (default, httpx +
  rate limiter, MRL truncation to 768 dims with re-normalization).
  `SentenceTransformerEmbedder` (offline escape hatch, guarded torch
  import). Startup probe validates dimension + unit norm.
- **`core/chunking.py`** — Greedy chunking from `SentenceUnit` atoms.
  Respects chapter boundaries, 900-char max, 1-unit overlap.
  `chunk_id = "{video_id}:c{index:04d}"`. Document text prefixed with
  chapter title for contextual grounding.
- **`core/vectorstore.py`** — Chroma `PersistentClient` wrapper with
  model-scoped collection names
  (`chunks__{slug(model)}_{dim}`). Upsert, query, delete. Full
  retrieval pipeline: recall (3x top_k) → dedupe → MMR (λ=0.7) →
  chronological sort.

**Tests**: 20 tests covering task types, output dimensionality,
re-normalization, batching, startup probe (dimension + norm mismatch),
connection errors, chapter boundary respect, overlap, chunk IDs, MMR
diversity, slug stability, collection naming.

### Phase 4 — Segmentation + verification + repair (`6af23e5`)

The core analysis phase — chapter boundary detection and validation:

- **`agents/segmentation.py`** — Hybrid deterministic + LLM approach:
  1. **Candidate detection** (no LLM): embed units, compute smoothed
     cosine distance between trailing/leading W=4 unit windows, take
     local maxima above mean + 0.8σ, enforce 45s minimum spacing.
  2. **LLM refinement**: render transcript as `[mm:ss] text` with `>>>`
     candidate markers, call LLM to endorse/add/remove boundaries.
     Windowing for long transcripts (45K char budget, 10% overlap,
     max 3 windows).
  3. **`build_chapters`** (deterministic): snap boundaries to nearest
     unit start, assign `chapter_id = "{video_id}:ch{idx:02d}"`.
- **`agents/verification.py`** — 12 deterministic rules (R1–R12):
  sorted, starts-at-zero, no-gaps, no-overlap, covers-end, within-bounds,
  min-duration (45s), max-duration (warning), count-range (3–25),
  title-present, summary-present, boundary-on-unit. **Does not import
  `core/llm`** — enforced by test.
- **Repair policy**: fixes applied in rule order. Too-short chapters
  merge into shorter neighbour. Too-many chapters merge shortest
  iteratively. Too-few chapters cannot be fixed (triggers resegment).
  Repair is idempotent and never calls an LLM.
- **`schemas/chapters.py`** — `ProposedBoundary`, `SegmentationOutput`,
  `Chapter`, `VerificationIssue`, `VerificationReport`, plus titling
  schemas (`ChapterCard`, `TitlingOutput`) defined for Phase 5.
- **`prompts/segmentation.md`** — prompt template for LLM boundary
  refinement.

**Tests**: 28 tests including one per verification rule, hypothesis
property test (random boundaries → build → repair → verify yields no
errors — the strongest correctness claim in the project), repair
idempotency, merge behaviour, candidate detection on synthetic topic
shifts, windowing, and the import boundary assertion.

---

## Remaining Phases

| Phase | Description | Status |
|-------|-------------|--------|
| 5 | Titling, entities, enrichment | Not started |
| 6 | Analysis graph + tracing (LangGraph) | Not started |
| 7 | Q&A graph | Not started |
| 8 | API + job runner | Not started |
| 9 | Frontend (Next.js) | Not started |
| 10 | Docker, deploy, docs, demo | Not started |

---

## Project Stats

| Metric | Count |
|--------|-------|
| Commits | 6 |
| Production modules | 38 |
| Test files | 14 |
| Total tests | 126 |
| Production lines of code | ~2,100 |
| Test lines of code | ~2,000 |

---

## Architecture Highlights

- **Provider-agnostic LLM layer**: swap between Gemini, OpenAI, Anthropic,
  or any OpenAI-compatible endpoint with zero code changes.
- **Asymmetric embeddings**: separate passage/query encoding via Gemini's
  `task_type` parameter — avoids the silent 10–20% retrieval quality loss
  from single-method embedders.
- **Hybrid segmentation**: deterministic candidate detection keeps token
  cost flat for long videos; LLM refinement adds judgment. More stable
  than pure-LLM segmentation.
- **Deterministic verification + repair**: 12-rule engine catches ~80% of
  segmentation defects mechanically. Only structural failures trigger
  expensive LLM re-prompts.
- **No live API calls in tests**: `FakeLLM` + `respx` mock everything.
  CI needs zero secrets.
- **Import boundaries enforced**: `litellm` only in `core/llm.py`,
  `verification.py` never imports LLM code, `torch` never on the default
  import path.
