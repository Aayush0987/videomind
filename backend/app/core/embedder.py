"""Embedding backend abstraction (§12.2). The only module allowed to talk to an embedding backend.

Defines the `Embedder` protocol plus `GeminiEmbedder` (default, everywhere)
and `SentenceTransformerEmbedder` (offline-development escape hatch, the
`[local]` extra only). Query and passage embedding are separate methods
because the model is asymmetric.
"""

import logging
import math
from typing import Protocol, runtime_checkable

import httpx

from app.config import settings
from app.core.errors import EmbeddingBackendUnavailable
from app.core.ratelimit import get_rate_limiter

logger = logging.getLogger(__name__)

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


@runtime_checkable
class Embedder(Protocol):
    name: str
    dim: int

    async def embed_passages(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


def _renormalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector))
    if norm < 1e-12:
        return vector
    return [x / norm for x in vector]


class GeminiEmbedder:
    """Default embedding backend — Gemini REST API via httpx."""

    def __init__(self) -> None:
        self.name = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM
        self._client = httpx.AsyncClient(timeout=30.0)
        self._limiter = get_rate_limiter("gemini", "embeddings", rpm=settings.GEMINI_EMBED_RPM)

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        all_vectors: list[list[float]] = []
        batch_size = settings.EMBEDDING_BATCH_SIZE
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            vectors = await self._batch_embed(batch, "RETRIEVAL_DOCUMENT")
            all_vectors.extend(vectors)
        return all_vectors

    async def embed_query(self, text: str) -> list[float]:
        await self._limiter.acquire()
        url = f"{_GEMINI_BASE}/models/{self.name}:embedContent"
        body = {
            "model": f"models/{self.name}",
            "content": {"parts": [{"text": text}]},
            "taskType": "RETRIEVAL_QUERY",
            "outputDimensionality": self.dim,
        }
        response = await self._request(url, body)
        vector = response["embedding"]["values"]
        return _renormalize(vector)

    async def _batch_embed(self, texts: list[str], task_type: str) -> list[list[float]]:
        await self._limiter.acquire()
        url = f"{_GEMINI_BASE}/models/{self.name}:batchEmbedContents"
        requests = [
            {
                "model": f"models/{self.name}",
                "content": {"parts": [{"text": t}]},
                "taskType": task_type,
                "outputDimensionality": self.dim,
            }
            for t in texts
        ]
        body = {"requests": requests}
        response = await self._request(url, body)
        return [_renormalize(e["values"]) for e in response["embeddings"]]

    async def _request(self, url: str, body: dict) -> dict:
        try:
            resp = await self._client.post(url, json=body, params={"key": settings.GEMINI_API_KEY})
        except httpx.ConnectError as exc:
            raise EmbeddingBackendUnavailable(
                f"Connection to Gemini embedding API failed: {exc}"
            ) from exc
        if resp.status_code != 200:
            raise EmbeddingBackendUnavailable(
                f"Gemini embedding API returned {resp.status_code}: {resp.text}"
            )
        return resp.json()


class SentenceTransformerEmbedder:
    """Offline-development escape hatch. Requires the [local] extra (torch)."""

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(settings.EMBEDDING_MODEL)
        self.name = settings.EMBEDDING_MODEL
        self.dim = settings.EMBEDDING_DIM

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, prompt_name="passage")
        return [_renormalize(v.tolist()) for v in embeddings]

    async def embed_query(self, text: str) -> list[float]:
        embeddings = self._model.encode([text], prompt_name="query")
        return _renormalize(embeddings[0].tolist())


_embedder: Embedder | None = None


def get_embedder() -> Embedder:
    """Lazy-init module-level singleton, resolved from EMBEDDING_BACKEND."""
    global _embedder  # noqa: PLW0603
    if _embedder is None:
        if settings.EMBEDDING_BACKEND == "gemini":
            _embedder = GeminiEmbedder()
        elif settings.EMBEDDING_BACKEND == "sentence_transformers":
            _embedder = SentenceTransformerEmbedder()
        else:
            raise ValueError(f"Unknown EMBEDDING_BACKEND: {settings.EMBEDDING_BACKEND}")
    return _embedder


def reset_embedder() -> None:
    """Test-only: clear the cached singleton."""
    global _embedder  # noqa: PLW0603
    _embedder = None


async def probe_embedder(embedder: Embedder) -> None:
    """Startup probe (§12.2.2): fail fast on dimension or norm mismatch."""
    vec = await embedder.embed_query("probe")
    if len(vec) != embedder.dim:
        raise RuntimeError(f"Embedder dimension mismatch: expected {embedder.dim}, got {len(vec)}")
    norm = math.sqrt(sum(x * x for x in vec))
    if abs(norm - 1.0) >= 1e-3:
        raise RuntimeError(f"Embedder norm mismatch: expected ~1.0, got {norm:.6f}")
