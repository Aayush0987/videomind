# Decisions

Append-only architectural decision log. Each entry is a fact and its
rationale. Newest entries at the bottom.

## 1. One embedding backend everywhere

The same embedding backend (`GeminiEmbedder`) runs locally and in
production. A laptop-hosted model would mean two incompatible vector
spaces, two seed-cache builds, and a whole class of invisible failure. One
backend everywhere removes all of it, and `gemini-embedding-001` outranks
the open models it would have replaced, so nothing is traded away on
quality. `SentenceTransformerEmbedder` stays in the codebase as a genuine
second implementation (the offline-development path) but is not the
default and is not built against in V1.

## 2. 768-dimension embedding lock

Embeddings are generated at 768 dimensions via `output_dimensionality`
(Matryoshka truncation from the model's native 3072). A single video is
~200–600 chunks, so the extra resolution of 1536 or 3072 buys nothing
measurable while costing 4x the index size and 4x the MMR arithmetic. This
dimension is chosen once and never changed — changing it later requires
re-embedding the entire corpus.

## 3. Reranking deferred out of V1

No cross-encoder reranker is built between the recall and MMR-diversity
stages of retrieval. Precision within the recalled set is handled by the
LLM-based grading agent instead, which can reason about sufficiency rather
than just pairwise similarity. A reranker is explicitly future work.

## 4. Opt into MLflow's file-store backend

`MLFLOW_TRACKING_URI` defaults to `file:./data/mlruns` so tracing needs no
infrastructure. MLflow 3.x puts the filesystem tracking backend in
"maintenance mode" and refuses to open it unless `MLFLOW_ALLOW_FILE_STORE`
is set. `core/tracing.run_context` sets that env var (via `setdefault`, so
a real deployment can still override the backend) immediately before
configuring the tracking URI. This keeps the zero-infrastructure local
setup working without introducing a database dependency.

## 5. Chapter-aware chunking over sentence units

`core/chunking.py` builds the retrieval chunks from the normalised
`SentenceUnit`s, never from raw characters, and never across a chapter
boundary:

- **Sentence units, not characters.** A chunk's `start`/`end` are the first
  unit's start and the last unit's end, so every citation timestamp lands
  on a real sentence boundary.
- **Chapter-scoped.** Units are assigned to the chapter whose range contains
  their start time, and chunks are built per chapter. A chunk therefore
  belongs to exactly one chapter and carries its `chapter_id`,
  `chapter_idx` and `chapter_title`, which the Q&A graph surfaces in
  citations and in the "closest topics" fallback.
- **Greedy up to `CHUNK_MAX_CHARS` (900)**, then start a new chunk that
  repeats the last `CHUNK_OVERLAP_UNITS` (1) unit(s), so a thought that
  straddles a chunk edge appears whole in at least one chunk.
- **Chapter title in the embedded text.** `doc_text` is the chapter title
  plus the chunk text, so the title contributes to the embedding.

Chunks are built after chapter verification, from the final chapters. The
two thresholds are code-level constants in `app/config.py`. Changing either
changes the index, so existing videos would need re-analysis.
