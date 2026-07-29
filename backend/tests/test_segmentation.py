"""Tests for agents/segmentation.py (§10.4, §18.2)."""

import ast
import inspect

import pytest
from app.agents.segmentation import build_chapters, detect_candidates, propose_boundaries
from app.core.llm import LLMConfig
from app.schemas.chapters import ProposedBoundary, SegmentationOutput
from app.schemas.transcript import SentenceUnit

from fakes.fake_llm import FakeLLM


def _unit(idx: int, start: float, end: float, text: str = "") -> SentenceUnit:
    return SentenceUnit(idx=idx, start=start, end=end, text=text or f"unit {idx}")


# ---------------------------------------------------------------------------
# detect_candidates: finds topic shifts
# ---------------------------------------------------------------------------


def test_detect_candidates_finds_topic_shifts() -> None:
    """Two distinct embedding clusters with a sharp boundary in the middle."""
    # 20 units: first 10 have embeddings pointing in one direction,
    # last 10 point in a very different direction.
    n = 20
    units = [_unit(i, float(i * 5), float(i * 5 + 5)) for i in range(n)]

    embeddings: list[list[float]] = []
    for i in range(n):
        if i < 10:
            embeddings.append([1.0, 0.0, 0.0])
        else:
            embeddings.append([0.0, 1.0, 0.0])

    candidates = detect_candidates(units, embeddings)

    # Should detect a boundary near unit 10 (timestamp 50.0)
    assert len(candidates) >= 1
    assert any(45.0 <= c <= 55.0 for c in candidates), (
        f"Expected boundary near 50.0, got {candidates}"
    )


def test_detect_candidates_enforces_min_spacing() -> None:
    """Two shifts close together — only the stronger one survives."""
    n = 30
    units = [_unit(i, float(i * 3), float(i * 3 + 3)) for i in range(n)]

    # Three clusters: [0-9] → shift → [10-19] → shift → [20-29]
    # but shifts at unit 10 (t=30) and unit 12 (t=36) are only 6s apart
    embeddings: list[list[float]] = []
    for i in range(n):
        if i < 10:
            embeddings.append([1.0, 0.0, 0.0])
        elif i < 12:
            embeddings.append([0.5, 0.5, 0.0])  # brief transition
        else:
            embeddings.append([0.0, 1.0, 0.0])

    candidates = detect_candidates(units, embeddings, min_spacing=45.0)

    # The two potential shifts are < 45s apart, so at most 1 survives
    assert len(candidates) <= 1


# ---------------------------------------------------------------------------
# build_chapters: deterministic boundary → chapter conversion
# ---------------------------------------------------------------------------


def test_build_chapters_snaps_and_prepends_zero() -> None:
    units = [_unit(i, float(i * 10), float(i * 10 + 10)) for i in range(30)]
    boundaries = [105.0, 205.0]  # will snap to 100.0, 200.0

    chapters = build_chapters("vid", boundaries, units, 300.0)

    assert chapters[0].start == 0.0
    assert chapters[0].chapter_id == "vid:ch00"
    assert len(chapters) == 3
    assert chapters[-1].end == 300.0


# ---------------------------------------------------------------------------
# propose_boundaries: windowing + LLM integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_windowing_triggers_above_char_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monkeypatch budget to a tiny value, verify LLM called multiple times."""
    import app.agents.segmentation as seg_module

    monkeypatch.setattr(seg_module, "SEGMENTATION_CHAR_BUDGET", 200)

    # Create enough units to exceed the tiny budget
    units = [_unit(i, float(i * 5), float(i * 5 + 5), f"word{i} " * 10) for i in range(40)]
    embeddings = [[1.0, 0.0, 0.0]] * 40  # uniform — no candidates
    duration = 200.0

    fake_llm = FakeLLM()
    # Register response by schema name so it works for any prompt text
    fake_llm.responses["SegmentationOutput"] = SegmentationOutput(
        boundaries=[ProposedBoundary(start=100.0, reason="topic shift")]
    )
    monkeypatch.setattr(seg_module, "generate_structured", fake_llm.generate_structured)

    cfg = LLMConfig()
    result = await propose_boundaries(units, embeddings, cfg, title="Test", duration=duration)

    # Should have called LLM more than once (windowing triggered)
    assert len(fake_llm.call_log) > 1
    # Result should contain the boundary from the canned response
    assert any(abs(b - 100.0) < 1.0 for b in result)


# ---------------------------------------------------------------------------
# Merge drops close boundaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_drops_close_boundaries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Boundaries within MIN_CHAPTER_SECONDS of each other — only one survives."""
    import app.agents.segmentation as seg_module

    fake_llm = FakeLLM()
    fake_llm.responses["SegmentationOutput"] = SegmentationOutput(
        boundaries=[
            ProposedBoundary(start=100.0, reason="shift A"),
            ProposedBoundary(start=110.0, reason="shift B"),  # only 10s after A
            ProposedBoundary(start=300.0, reason="shift C"),
        ]
    )
    monkeypatch.setattr(seg_module, "generate_structured", fake_llm.generate_structured)

    units = [_unit(i, float(i * 5), float(i * 5 + 5)) for i in range(100)]
    embeddings = [[1.0, 0.0, 0.0]] * 100  # uniform — no candidates
    cfg = LLMConfig()

    result = await propose_boundaries(units, embeddings, cfg, title="Test", duration=500.0)

    # 100.0 and 110.0 are < 45s apart — at most one should survive
    close_pair = [b for b in result if 95.0 <= b <= 115.0]
    assert len(close_pair) <= 1
    # 300.0 should survive
    assert any(abs(b - 300.0) < 1.0 for b in result)


# ---------------------------------------------------------------------------
# Import boundary: verification.py must not import core.llm
# ---------------------------------------------------------------------------


def test_verification_does_not_import_llm() -> None:
    import app.agents.verification as mod

    source = inspect.getsource(mod)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "core.llm" not in alias.name, f"verification.py imports {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "core.llm" not in module, f"verification.py imports from {module}"
