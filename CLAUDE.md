# VideoMind

Agentic video intelligence platform. Paste a YouTube link, get topic-based
chapters and an agentic-RAG Q&A with clickable timestamp citations.

The authoritative build spec is `docs/VIDEOMIND_IMPLEMENTATION_PLAN.md`.
Read the sections relevant to the current phase before writing any code.

## Hard rules

- Build strictly in the §22 phase order. Never start a phase before the
  previous phase's verify command passes.
- Every schema, endpoint, filename, env var, and threshold in the plan is
  normative. Do not rename things. Do not invent extra ones.
- Follow the coding standards in §3: simple and linear, no speculative
  abstraction, no defensive try/except, no dead code, no hardcoded values.
  All config flows through `app/config.py`.
- Import boundaries, enforced by tests:
  - Only `core/llm.py` may import `litellm`.
  - Only `core/embedder.py` may talk to an embedding backend.
  - `agents/verification.py` must not import anything from `core/llm.py`.
  - Nothing in the default import path may pull in `torch`.
- Do NOT build a cross-encoder reranker. It is explicitly out of V1 (§25.2).
- Never write an API key to a log line, a test fixture, a commit, MLflow,
  or any file other than a gitignored `.env`.
- Prompts live in `app/prompts/*.md`, never inline in Python.
- If you hit a real blocker, stop, append a note to `docs/DECISIONS.md`,
  and take the documented fallback in §21.2. Do not silently redesign.
- Commit at the end of each phase: `phase(N): <short description>`.

## Environment

- macOS, Apple Silicon. Python 3.11, Node 18+.
- One Gemini API key powers both the LLM and the embeddings.
- Embeddings: `gemini-embedding-001` at 768 dimensions, locked. The same
  backend runs locally and in production — there is no second vector space.
- Re-normalise embedding vectors after MRL truncation. Assert unit norm.
- No local ML dependencies. Nothing imports torch.

## Commands

- `make lint`  — ruff check + format check
- `make test`  — pytest
- `make dev`   — run the backend locally
- `make mlflow`— open the local MLflow UI