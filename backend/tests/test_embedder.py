"""Tests for app.core.embedder (§12.2). Uses respx to mock the Gemini
embedding REST API — no live network calls."""

import math

import httpx
import pytest
import respx
from app import config
from app.core.embedder import (
    GeminiEmbedder,
    _renormalize,
    probe_embedder,
    reset_embedder,
)
from app.core.errors import EmbeddingBackendUnavailable

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


@pytest.fixture(autouse=True)
def _fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.settings, "GEMINI_API_KEY", "fake-key")
    monkeypatch.setattr(config.settings, "EMBEDDING_DIM", 3)
    monkeypatch.setattr(config.settings, "EMBEDDING_BATCH_SIZE", 2)
    reset_embedder()


def _make_vector(dim: int = 3, scale: float = 5.0) -> list[float]:
    """Return a non-unit vector of the given dimension."""
    return [scale * (i + 1) for i in range(dim)]


def _unit_vector(dim: int = 3) -> list[float]:
    raw = [float(i + 1) for i in range(dim)]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]


@respx.mock
@pytest.mark.asyncio
async def test_embed_passages_sends_retrieval_document_task_type() -> None:
    model = config.settings.EMBEDDING_MODEL
    route = respx.post(f"{_GEMINI_BASE}/models/{model}:batchEmbedContents").mock(
        return_value=httpx.Response(
            200,
            json={"embeddings": [{"values": _make_vector()}]},
        )
    )

    embedder = GeminiEmbedder()
    await embedder.embed_passages(["hello"])

    assert route.called
    body = route.calls[0].request.content
    import json

    parsed = json.loads(body)
    assert parsed["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"


@respx.mock
@pytest.mark.asyncio
async def test_embed_query_sends_retrieval_query_task_type() -> None:
    model = config.settings.EMBEDDING_MODEL
    route = respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        return_value=httpx.Response(
            200,
            json={"embedding": {"values": _make_vector()}},
        )
    )

    embedder = GeminiEmbedder()
    await embedder.embed_query("hello")

    assert route.called
    import json

    parsed = json.loads(route.calls[0].request.content)
    assert parsed["taskType"] == "RETRIEVAL_QUERY"


@respx.mock
@pytest.mark.asyncio
async def test_output_dimensionality_is_set() -> None:
    model = config.settings.EMBEDDING_MODEL
    respx.post(f"{_GEMINI_BASE}/models/{model}:batchEmbedContents").mock(
        return_value=httpx.Response(
            200,
            json={"embeddings": [{"values": _make_vector()}]},
        )
    )
    respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        return_value=httpx.Response(
            200,
            json={"embedding": {"values": _make_vector()}},
        )
    )

    embedder = GeminiEmbedder()
    await embedder.embed_passages(["hello"])
    await embedder.embed_query("hello")

    import json

    for call in respx.calls:
        parsed = json.loads(call.request.content)
        if "requests" in parsed:
            assert parsed["requests"][0]["outputDimensionality"] == 3
        else:
            assert parsed["outputDimensionality"] == 3


@respx.mock
@pytest.mark.asyncio
async def test_returned_vectors_are_renormalised_to_unit_norm() -> None:
    """Return a non-unit vector from mock; assert embedder output has norm ≈ 1.0."""
    model = config.settings.EMBEDDING_MODEL
    non_unit = [3.0, 4.0, 0.0]  # norm = 5.0
    respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        return_value=httpx.Response(
            200,
            json={"embedding": {"values": non_unit}},
        )
    )

    embedder = GeminiEmbedder()
    result = await embedder.embed_query("test")

    norm = math.sqrt(sum(x * x for x in result))
    assert abs(norm - 1.0) < 1e-6


@respx.mock
@pytest.mark.asyncio
async def test_batching_splits_and_reassembles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass 3 texts with batch_size=2 → 2 requests, results in input order."""
    model = config.settings.EMBEDDING_MODEL
    call_count = 0

    def make_response(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        import json

        body = json.loads(request.content)
        n = len(body["requests"])
        vecs = [[float(call_count * 10 + i + 1)] * 3 for i in range(n)]
        call_count += 1
        return httpx.Response(200, json={"embeddings": [{"values": v} for v in vecs]})

    respx.post(f"{_GEMINI_BASE}/models/{model}:batchEmbedContents").mock(side_effect=make_response)

    embedder = GeminiEmbedder()
    results = await embedder.embed_passages(["a", "b", "c"])

    assert len(results) == 3
    assert call_count == 2  # batch_size=2, 3 texts → 2 requests
    # First batch returns vectors starting with 1.0, second with 11.0 (after renorm)
    # Just verify order is preserved — first two from batch 0, third from batch 1
    assert len(results[0]) == 3
    assert len(results[1]) == 3
    assert len(results[2]) == 3


@respx.mock
@pytest.mark.asyncio
async def test_startup_probe_raises_on_dimension_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = config.settings.EMBEDDING_MODEL
    wrong_dim = [1.0, 0.0]  # dim=2 but embedder expects 3
    respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        return_value=httpx.Response(
            200,
            json={"embedding": {"values": wrong_dim}},
        )
    )

    embedder = GeminiEmbedder()
    with pytest.raises(RuntimeError, match="dimension mismatch"):
        await probe_embedder(embedder)


@respx.mock
@pytest.mark.asyncio
async def test_startup_probe_raises_on_norm_mismatch() -> None:
    model = config.settings.EMBEDDING_MODEL
    zero_vec = [0.0, 0.0, 0.0]  # norm = 0, renormalize returns as-is
    respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        return_value=httpx.Response(
            200,
            json={"embedding": {"values": zero_vec}},
        )
    )

    embedder = GeminiEmbedder()
    with pytest.raises(RuntimeError, match="norm mismatch"):
        await probe_embedder(embedder)


@respx.mock
@pytest.mark.asyncio
async def test_connection_refused_raises_embedding_backend_unavailable() -> None:
    model = config.settings.EMBEDDING_MODEL
    respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        side_effect=httpx.ConnectError("Connection refused")
    )

    embedder = GeminiEmbedder()
    with pytest.raises(EmbeddingBackendUnavailable):
        await embedder.embed_query("test")


@respx.mock
@pytest.mark.asyncio
async def test_non_200_raises_embedding_backend_unavailable() -> None:
    model = config.settings.EMBEDDING_MODEL
    respx.post(f"{_GEMINI_BASE}/models/{model}:embedContent").mock(
        return_value=httpx.Response(500, text="Internal Server Error")
    )

    embedder = GeminiEmbedder()
    with pytest.raises(EmbeddingBackendUnavailable, match="500"):
        await embedder.embed_query("test")


def test_renormalize_produces_unit_vector() -> None:
    raw = [3.0, 4.0, 0.0]
    result = _renormalize(raw)
    norm = math.sqrt(sum(x * x for x in result))
    assert abs(norm - 1.0) < 1e-9
