# Decisions

Append-only architectural decision log. Each entry is a fact, its
rationale, and the section of `docs/VIDEOMIND_IMPLEMENTATION_PLAN.md` that
governs it. Newest entries at the bottom.

## 1. One embedding backend everywhere

The same embedding backend (`GeminiEmbedder`) runs locally and in
production. A laptop-hosted model would mean two incompatible vector
spaces, two seed-cache builds, and a whole class of invisible failure. One
backend everywhere removes all of it, and `gemini-embedding-001` outranks
the open models it would have replaced, so nothing is traded away on
quality. `SentenceTransformerEmbedder` stays in the codebase as a genuine
second implementation (the offline-development path) but is not the
default and is not built against in V1.

See §12.2.

## 2. 768-dimension embedding lock

Embeddings are generated at 768 dimensions via `output_dimensionality`
(Matryoshka truncation from the model's native 3072). A single video is
~200–600 chunks, so the extra resolution of 1536 or 3072 buys nothing
measurable while costing 4x the index size and 4x the MMR arithmetic. This
dimension is chosen once and never changed — changing it later requires
re-embedding the entire corpus.

See §12.2.1.

## 3. Reranking deferred out of V1

No cross-encoder reranker is built between the recall and MMR-diversity
stages of retrieval. Precision within the recalled set is handled by the
LLM-based grading agent instead, which can reason about sufficiency rather
than just pairwise similarity. A reranker is explicitly future work.

See §25.2.

## 4. Opt into MLflow's file-store backend

The plan pins `MLFLOW_TRACKING_URI=file:./data/mlruns` for the free tier
(§17, §19), but MLflow 3.x puts the filesystem tracking backend in
"maintenance mode" and refuses to open it unless `MLFLOW_ALLOW_FILE_STORE`
is set. `core/tracing.run_context` sets that env var (via `setdefault`, so
a real deployment can still override the backend) immediately before
configuring the tracking URI. This keeps the documented zero-infrastructure
local/free-tier setup working without introducing a database dependency.

See §17.
