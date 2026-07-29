"""Tests for the repair policy in agents/verification.py (§11.2)."""

from app.agents.verification import repair_chapters, verify_chapters
from app.schemas.chapters import Chapter
from app.schemas.transcript import SentenceUnit


def _unit(idx: int, start: float, end: float) -> SentenceUnit:
    return SentenceUnit(idx=idx, start=start, end=end, text=f"unit {idx}")


def _make_units(duration: float, step: float = 5.0) -> list[SentenceUnit]:
    units: list[SentenceUnit] = []
    t = 0.0
    idx = 0
    while t < duration:
        end = min(t + step, duration)
        units.append(_unit(idx, t, end))
        t = end
        idx += 1
    return units


def _ch(idx: int, start: float, end: float, *, title: str = "", video_id: str = "vid") -> Chapter:
    return Chapter(
        chapter_id=f"{video_id}:ch{idx:02d}",
        idx=idx,
        start=start,
        end=end,
        title=title,
    )


_DURATION = 600.0
_UNITS = _make_units(_DURATION)


def test_repair_fixes_broken_segmentation() -> None:
    """Multiple violations (unsorted, gap, boundary off-unit) → repair → valid."""
    chapters = [
        _ch(1, 200.0, 390.0),  # gap before next (R3)
        _ch(0, 3.0, 200.0),  # not sorted (R1), doesn't start at 0 (R2)
        _ch(2, 400.0, 500.0),  # doesn't cover end (R5)
    ]
    repaired, report = repair_chapters(chapters, _DURATION, _UNITS)

    assert report.repaired
    # After repair, only warnings should remain
    error_issues = [i for i in report.issues if i.severity == "error"]
    assert error_issues == [], f"Errors remain: {error_issues}"
    assert repaired[0].start == 0.0
    assert repaired[-1].end == _DURATION
    assert all(repaired[i].end == repaired[i + 1].start for i in range(len(repaired) - 1))


def test_too_few_chapters_not_fixable() -> None:
    """2 chapters for 600s video → repair sets repaired=True but valid=False."""
    chapters = [_ch(0, 0.0, 300.0), _ch(1, 300.0, 600.0)]
    repaired, report = repair_chapters(chapters, _DURATION, _UNITS)

    assert report.repaired
    assert not report.valid
    assert any(i.rule == "R9_count_range" and i.severity == "error" for i in report.issues)


def test_repair_is_idempotent() -> None:
    """Valid chapters → repair → same output, repaired=True."""
    chapters = [
        _ch(0, 0.0, 200.0),
        _ch(1, 200.0, 400.0),
        _ch(2, 400.0, 600.0),
    ]
    # Verify they're valid first
    pre_report = verify_chapters(chapters, _DURATION, _UNITS)
    assert pre_report.valid

    repaired, report = repair_chapters(chapters, _DURATION, _UNITS)
    assert report.repaired
    assert report.valid
    # Chapter structure unchanged
    assert len(repaired) == len(chapters)
    for orig, fixed in zip(chapters, repaired, strict=True):
        assert orig.start == fixed.start
        assert orig.end == fixed.end


def test_repair_merges_short_chapter_into_shorter_neighbour() -> None:
    """A 20s chapter between 280s and 300s neighbours merges into the shorter one."""
    chapters = [
        _ch(0, 0.0, 100.0),  # 100s
        _ch(1, 100.0, 120.0),  # 20s — too short
        _ch(2, 120.0, 400.0),  # 280s
        _ch(3, 400.0, 600.0),  # 200s
    ]
    repaired, report = repair_chapters(chapters, _DURATION, _UNITS)

    assert report.repaired
    # The short chapter should have been merged into ch0 (shorter neighbour)
    assert len(repaired) == 3
    assert repaired[0].end == repaired[1].start
