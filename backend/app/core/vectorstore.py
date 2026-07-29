"""Chroma persistent client wrapper: collection naming, upsert, and query (§12.3).

Also contains the retrieval pipeline (§12.4): recall → dedupe → MMR → sort.
"""

import math
import re
from pathlib import Path

import chromadb

from app.config import MMR_LAMBDA, settings
from app.core.chunking import Chunk
from app.core.embedder import Embedder


def slug(name: str) -> str:
    """Stable slug: lowercase, non-alphanumeric replaced with underscore."""
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


class VectorStore:
    """Thin Chroma wrapper with model-scoped collection names."""

    def __init__(self, embedder: Embedder) -> None:
        chroma_path = str(Path(settings.DATA_DIR) / "chroma")
        self._client = chromadb.PersistentClient(path=chroma_path)
        collection_name = f"chunks__{slug(embedder.name)}_{embedder.dim}"
        self._collection = self._client.get_or_create_collection(
            name=collection_name, embedding_function=None
        )
        self.collection_name = collection_name

    def upsert(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        self._collection.upsert(
            ids=[c.chunk_id for c in chunks],
            documents=[c.doc_text for c in chunks],
            metadatas=[
                {
                    "video_id": c.video_id,
                    "chapter_id": c.chapter_id,
                    "chapter_idx": c.chapter_idx,
                    "chapter_title": c.chapter_title,
                    "start": c.start,
                    "end": c.end,
                    "unit_start_idx": c.unit_start_idx,
                    "unit_end_idx": c.unit_end_idx,
                }
                for c in chunks
            ],
            embeddings=embeddings,
        )

    def query(self, query_embedding: list[float], video_id: str, n_results: int) -> list[dict]:
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where={"video_id": video_id},
        )
        items = []
        for i in range(len(results["ids"][0])):
            items.append(
                {
                    "chunk_id": results["ids"][0][i],
                    "distance": results["distances"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "document": results["documents"][0][i],
                }
            )
        return items

    def delete_video(self, video_id: str) -> None:
        self._collection.delete(where={"video_id": video_id})


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def _mmr(
    query_vec: list[float],
    candidates: list[dict],
    top_k: int,
    lambda_: float = MMR_LAMBDA,
) -> list[dict]:
    """Maximal Marginal Relevance selection (~20 lines, per §12.4)."""
    if not candidates:
        return []

    doc_vecs = [c["_embedding"] for c in candidates]
    selected: list[int] = []
    remaining = list(range(len(candidates)))

    for _ in range(min(top_k, len(remaining))):
        best_idx = max(
            remaining,
            key=lambda i: (
                lambda_ * _cosine_sim(query_vec, doc_vecs[i])
                - (1 - lambda_)
                * (
                    max(
                        (_cosine_sim(doc_vecs[i], doc_vecs[j]) for j in selected),
                        default=0.0,
                    )
                )
            ),
        )
        selected.append(best_idx)
        remaining.remove(best_idx)

    return [candidates[i] for i in selected]


def retrieve(
    store: VectorStore,
    query_embedding: list[float],
    video_id: str,
    top_k: int,
) -> list[dict]:
    """Full retrieval pipeline: recall → dedupe → MMR → chronological sort."""
    # 1. Recall
    raw = store.query(query_embedding, video_id, n_results=3 * top_k)

    if not raw:
        return []

    # 2. Dedupe by chunk_id, keeping best (smallest) distance
    seen: dict[str, dict] = {}
    for item in raw:
        cid = item["chunk_id"]
        if cid not in seen or item["distance"] < seen[cid]["distance"]:
            seen[cid] = item
    deduped = list(seen.values())

    # 3. MMR — need embeddings for diversity scoring
    # Chroma returns embeddings=None by default in query; we re-query with include
    # For MMR, we use the distance as a proxy: Chroma L2 distance for unit-norm
    # vectors relates to cosine sim as: cos_sim = 1 - dist²/2.
    # But for proper MMR we need the actual vectors. Since our vectors are
    # unit-normalised and stored in Chroma, we fetch them.
    results_with_emb = store._collection.query(
        query_embeddings=[query_embedding],
        n_results=3 * top_k,
        where={"video_id": video_id},
        include=["embeddings", "metadatas", "documents", "distances"],
    )
    emb_by_id: dict[str, list[float]] = {}
    for i in range(len(results_with_emb["ids"][0])):
        emb_by_id[results_with_emb["ids"][0][i]] = results_with_emb["embeddings"][0][i]

    for item in deduped:
        item["_embedding"] = emb_by_id.get(item["chunk_id"], [])

    selected = _mmr(query_embedding, deduped, top_k)

    # Clean up internal field
    for item in selected:
        item.pop("_embedding", None)

    # 4. Order by start (chronological)
    selected.sort(key=lambda x: x["metadata"]["start"])

    return selected
