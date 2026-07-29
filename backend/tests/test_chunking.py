"""Tests for app.core.chunking (§12.1), MMR (§12.4), and collection naming (§12.3)."""

from app.core.chunking import ChapterRange, build_chunks
from app.core.vectorstore import _cosine_sim, _mmr, slug
from app.schemas.transcript import SentenceUnit


def _unit(idx: int, start: float, end: float, text: str) -> SentenceUnit:
    return SentenceUnit(idx=idx, start=start, end=end, text=text)


def _chapter(chapter_id: str, idx: int, title: str, start: float, end: float) -> ChapterRange:
    return ChapterRange(
        chapter_id=chapter_id,
        chapter_idx=idx,
        chapter_title=title,
        start=start,
        end=end,
    )


# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------


def test_chunks_never_cross_chapter_boundary() -> None:
    units = [
        _unit(0, 0.0, 5.0, "A" * 400),
        _unit(1, 5.0, 10.0, "B" * 400),
        _unit(2, 10.0, 15.0, "C" * 400),
        _unit(3, 15.0, 20.0, "D" * 400),
        _unit(4, 20.0, 25.0, "E" * 400),
        _unit(5, 25.0, 30.0, "F" * 400),
    ]
    ch1 = _chapter("ch0", 0, "First", 0.0, 15.0)
    ch2 = _chapter("ch1", 1, "Second", 15.0, 30.0)

    chunks = build_chunks("vid", units, [ch1, ch2])

    for chunk in chunks:
        if chunk.chapter_id == "ch0":
            assert chunk.start >= 0.0
            assert chunk.end <= 15.0
        elif chunk.chapter_id == "ch1":
            assert chunk.start >= 15.0
            assert chunk.end <= 30.0


def test_overlap_is_present() -> None:
    """Last unit of chunk N appears as first unit of chunk N+1 (CHUNK_OVERLAP_UNITS=1)."""
    units = [_unit(i, float(i * 5), float(i * 5 + 5), f"word{i} " * 50) for i in range(10)]
    chapter = _chapter("ch0", 0, "All", 0.0, 50.0)

    chunks = build_chunks("vid", units, [chapter])

    assert len(chunks) > 1
    for i in range(len(chunks) - 1):
        current_end_idx = chunks[i].unit_end_idx
        next_start_idx = chunks[i + 1].unit_start_idx
        assert next_start_idx == current_end_idx, (
            f"chunk {i} ends at unit {current_end_idx}, "
            f"chunk {i + 1} starts at unit {next_start_idx} — expected overlap"
        )


def test_chunk_ids_are_unique_and_ordered() -> None:
    units = [_unit(i, float(i * 5), float(i * 5 + 5), f"text{i} " * 50) for i in range(10)]
    chapter = _chapter("ch0", 0, "All", 0.0, 50.0)

    chunks = build_chunks("vid", units, [chapter])

    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids)), "chunk_ids are not unique"
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_id == f"vid:c{i:04d}"


def test_single_synthetic_chapter() -> None:
    units = [_unit(i, float(i), float(i + 1), f"unit {i}") for i in range(20)]
    chapter = _chapter("ch0", 0, "Full Video", 0.0, 20.0)

    chunks = build_chunks("vid", units, [chapter])

    assert len(chunks) >= 1
    all_unit_idxs = set()
    for c in chunks:
        for idx in range(c.unit_start_idx, c.unit_end_idx + 1):
            all_unit_idxs.add(idx)
    assert all_unit_idxs == set(range(20))


def test_doc_text_is_prefixed_with_chapter_title() -> None:
    units = [_unit(0, 0.0, 5.0, "Some content here.")]
    chapter = _chapter("ch0", 0, "My Chapter", 0.0, 5.0)

    chunks = build_chunks("vid", units, [chapter])

    assert chunks[0].doc_text == "My Chapter\nSome content here."


# ---------------------------------------------------------------------------
# MMR tests
# ---------------------------------------------------------------------------


def test_mmr_selects_distinct_before_fourth_duplicate() -> None:
    """Five near-identical vectors + one distinct → distinct selected before 4th dup."""
    query = [1.0, 0.0, 0.0]
    # Five near-identical passages clustered around [0.8, 0.6, 0] — all equally
    # relevant to query, nearly identical to each other.
    near_copies = [[0.8, 0.6 + 0.001 * i, 0.0] for i in range(5)]
    # One passage equally relevant to query but far from the cluster.
    distinct = [0.8, -0.6, 0.0]

    all_vecs = near_copies + [distinct]
    candidates = [
        {"chunk_id": f"c{i}", "_embedding": v, "distance": 1 - _cosine_sim(query, v)}
        for i, v in enumerate(all_vecs)
    ]

    selected = _mmr(query, candidates, top_k=6, lambda_=0.7)
    selected_ids = [s["chunk_id"] for s in selected]

    # The distinct vector ("c5") should appear before the 4th near-duplicate
    distinct_pos = selected_ids.index("c5")
    assert distinct_pos < 4, f"Distinct vector selected at position {distinct_pos}, expected < 4"


# ---------------------------------------------------------------------------
# Collection naming tests
# ---------------------------------------------------------------------------


def test_slug_is_stable() -> None:
    assert slug("gemini-embedding-001") == "gemini_embedding_001"


def test_slug_handles_special_chars() -> None:
    assert slug("Model.Name/v2") == "model_name_v2"


def test_different_dims_produce_different_collection_names() -> None:
    name_768 = f"chunks__{slug('gemini-embedding-001')}_768"
    name_256 = f"chunks__{slug('gemini-embedding-001')}_256"
    assert name_768 != name_256
    assert name_768 == "chunks__gemini_embedding_001_768"
    assert name_256 == "chunks__gemini_embedding_001_256"


def test_different_models_produce_different_collection_names() -> None:
    name_a = f"chunks__{slug('gemini-embedding-001')}_768"
    name_b = f"chunks__{slug('all-MiniLM-L6-v2')}_768"
    assert name_a != name_b
