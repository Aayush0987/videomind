# VideoMind

Agentic video intelligence platform. Paste a YouTube link, get topic-based
chapters and an agentic-RAG Q&A with clickable timestamp citations.

V1 is built. `README.md` is the authoritative reference for what this
project is, how it's architected, and how to run it.

## Hard rules

- Every schema, endpoint, filename, env var, and threshold already in use
  is normative. Do not rename things without a reason tied to an actual
  bug. Do not invent extra ones.
- Follow the coding standards: simple and linear, no speculative
  abstraction, no defensive try/except, no dead code, no hardcoded values.
  All config flows through `app/config.py`.
- Import boundaries, enforced by tests:
  - Only `core/llm.py` may import `litellm`.
  - Only `core/embedder.py` may talk to an embedding backend.
  - `agents/verification.py` must not import anything from `core/llm.py`.
  - Nothing in the default import path may pull in `torch`.
- Do NOT build a cross-encoder reranker. It is explicitly out of scope.
- Never write an API key to a log line, a test fixture, a commit, MLflow,
  or any file other than a gitignored `.env`.
- Prompts live in `app/prompts/*.md`, never inline in Python.

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