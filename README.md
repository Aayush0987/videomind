# VideoMind

Agentic video intelligence platform. Paste a YouTube link, get topic-based
chapters and an agentic-RAG Q&A with clickable timestamp citations.

The authoritative build spec is
[`docs/VIDEOMIND_IMPLEMENTATION_PLAN.md`](docs/VIDEOMIND_IMPLEMENTATION_PLAN.md).
Build order and phase gates are in `docs/VIDEOMIND_IMPLEMENTATION_PLAN.md` §22.
Architectural decisions are logged in [`docs/DECISIONS.md`](docs/DECISIONS.md).

**Status:** Phase 0 (scaffold) — no application logic yet.

## Commands

- `make lint`   — ruff check + format check
- `make test`   — pytest
- `make dev`    — run the backend locally
- `make mlflow` — open the local MLflow UI

## Setup

1. `cd backend && pip install -e ".[dev]"`
2. Copy `.env.example` to `.env` and fill in the values you need.
3. `make test`
