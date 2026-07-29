"""Tests for agents/verification.py — one test per rule R1–R12 + hypothesis property (§11.3)."""

import hypothesis.strategies as st
from app.agents.segmentation import build_chapters
from app.agents.verification import repair_chapters, verify_chapters
from app.schemas.chapters import Chapter
from app.schemas.transcript import SentenceUnit
from hypothesis import assume, given
from hypothesis import settings as h_settings


def _unit(idx: int, start: float, end: float) -> SentenceUnit:
    return SentenceUnit(idx=idx, start=start, end=end, text=f"unit {idx}")


def _make_units(duration: float, step: float = 5.0) -> list[SentenceUnit]:
    """Create synthetic units every *step* seconds."""
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


# ---------------------------------------------------------------------------
# R1: chapters strictly ordered by start
# ---------------------------------------------------------------------------


def test_r1_unsorted() -> None:
    chapters = [_ch(0, 200.0, 400.0), _ch(1, 0.0, 200.0), _ch(2, 400.0, 600.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R1_sorted" for i in report.issues)


# ---------------------------------------------------------------------------
# R2: first chapter starts at (or near) zero
# ---------------------------------------------------------------------------


def test_r2_does_not_start_at_zero() -> None:
    chapters = [_ch(0, 5.0, 200.0), _ch(1, 200.0, 400.0), _ch(2, 400.0, 600.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R2_starts_at_zero" for i in report.issues)


# ---------------------------------------------------------------------------
# R3: no gaps > 1.0s
# ---------------------------------------------------------------------------


def test_r3_gap() -> None:
    chapters = [_ch(0, 0.0, 190.0), _ch(1, 200.0, 400.0), _ch(2, 400.0, 600.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R3_no_gaps" for i in report.issues)


# ---------------------------------------------------------------------------
# R4: no overlap
# ---------------------------------------------------------------------------


def test_r4_overlap() -> None:
    chapters = [_ch(0, 0.0, 250.0), _ch(1, 200.0, 400.0), _ch(2, 400.0, 600.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R4_no_overlap" for i in report.issues)


# ---------------------------------------------------------------------------
# R5: last chapter covers the end
# ---------------------------------------------------------------------------


def test_r5_does_not_cover_end() -> None:
    chapters = [_ch(0, 0.0, 200.0), _ch(1, 200.0, 400.0), _ch(2, 400.0, 500.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R5_covers_end" for i in report.issues)


# ---------------------------------------------------------------------------
# R6: within bounds
# ---------------------------------------------------------------------------


def test_r6_out_of_bounds() -> None:
    chapters = [_ch(0, -5.0, 200.0), _ch(1, 200.0, 400.0), _ch(2, 400.0, 600.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R6_within_bounds" for i in report.issues)


# ---------------------------------------------------------------------------
# R7: minimum duration
# ---------------------------------------------------------------------------


def test_r7_too_short() -> None:
    chapters = [
        _ch(0, 0.0, 20.0),
        _ch(1, 20.0, 200.0),
        _ch(2, 200.0, 400.0),
        _ch(3, 400.0, 600.0),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R7_min_duration" for i in report.issues)


# ---------------------------------------------------------------------------
# R8: maximum duration (warning)
# ---------------------------------------------------------------------------


def test_r8_too_long() -> None:
    # Duration 600s → max_dur = max(900, 0.35*600) = 900
    # Need a chapter > 900s, so use a longer duration
    duration = 5000.0
    units = _make_units(duration)
    # max_dur = max(900, 0.35*5000) = 1750
    chapters = [
        _ch(0, 0.0, 2000.0),
        _ch(1, 2000.0, 3500.0),
        _ch(2, 3500.0, 5000.0),
    ]
    report = verify_chapters(chapters, duration, units)
    assert any(i.rule == "R8_max_duration" and i.severity == "warning" for i in report.issues)


# ---------------------------------------------------------------------------
# R9: count range
# ---------------------------------------------------------------------------


def test_r9_too_many() -> None:
    # 30 chapters for 600s → max_by_duration = 600/45 = 13
    chapters = [_ch(i, i * 20.0, (i + 1) * 20.0) for i in range(30)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R9_count_range" for i in report.issues)


def test_r9_too_few() -> None:
    chapters = [_ch(0, 0.0, 300.0), _ch(1, 300.0, 600.0)]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert not report.valid
    assert any(i.rule == "R9_count_range" for i in report.issues)


# ---------------------------------------------------------------------------
# R10: title present (after titling only)
# ---------------------------------------------------------------------------


def test_r10_empty_title_after_titling() -> None:
    chapters = [
        _ch(0, 0.0, 200.0),
        _ch(1, 200.0, 400.0),
        _ch(2, 400.0, 600.0),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS, after_titling=True)
    assert not report.valid
    assert any(i.rule == "R10_title_present" for i in report.issues)


def test_r10_skipped_before_titling() -> None:
    """Empty titles do NOT trigger R10 before titling."""
    chapters = [
        _ch(0, 0.0, 200.0),
        _ch(1, 200.0, 400.0),
        _ch(2, 400.0, 600.0),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS, after_titling=False)
    assert not any(i.rule == "R10_title_present" for i in report.issues)


def test_r10_duplicate_titles() -> None:
    chapters = [
        _ch(0, 0.0, 200.0, title="Same Title"),
        _ch(1, 200.0, 400.0, title="Same Title"),
        _ch(2, 400.0, 600.0, title="Different"),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS, after_titling=True)
    assert not report.valid
    assert any(i.rule == "R10_title_present" and "duplicate" in i.detail for i in report.issues)


# ---------------------------------------------------------------------------
# R11: summary present (after titling only)
# ---------------------------------------------------------------------------


def test_r11_missing_summary_after_titling() -> None:
    chapters = [
        _ch(0, 0.0, 200.0, title="A"),
        _ch(1, 200.0, 400.0, title="B"),
        _ch(2, 400.0, 600.0, title="C"),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS, after_titling=True)
    assert any(i.rule == "R11_summary_present" for i in report.issues)


def test_r11_skipped_before_titling() -> None:
    chapters = [
        _ch(0, 0.0, 200.0),
        _ch(1, 200.0, 400.0),
        _ch(2, 400.0, 600.0),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS, after_titling=False)
    assert not any(i.rule == "R11_summary_present" for i in report.issues)


# ---------------------------------------------------------------------------
# R12: boundary on unit
# ---------------------------------------------------------------------------


def test_r12_boundary_not_on_unit() -> None:
    units = [_unit(0, 0.0, 5.0), _unit(1, 5.0, 10.0)]
    chapters = [
        _ch(0, 0.0, 200.0),
        _ch(1, 200.0, 400.0),
        _ch(2, 400.0, 600.0),
    ]
    report = verify_chapters(chapters, _DURATION, units)
    assert any(i.rule == "R12_boundary_on_unit" and i.severity == "warning" for i in report.issues)


# ---------------------------------------------------------------------------
# Valid chapters produce a clean report
# ---------------------------------------------------------------------------


def test_valid_chapters_pass() -> None:
    chapters = [
        _ch(0, 0.0, 200.0),
        _ch(1, 200.0, 400.0),
        _ch(2, 400.0, 600.0),
    ]
    report = verify_chapters(chapters, _DURATION, _UNITS)
    assert report.valid


# ---------------------------------------------------------------------------
# Hypothesis property test (§11.3)
# ---------------------------------------------------------------------------


@given(
    raw_boundaries=st.lists(
        st.floats(min_value=0.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
        min_size=3,
        max_size=30,
    ),
    duration=st.floats(min_value=180.0, max_value=3600.0, allow_nan=False, allow_infinity=False),
)
@h_settings(max_examples=200)
def test_repair_always_produces_valid_or_warning_only(
    raw_boundaries: list[float], duration: float
) -> None:
    """For any random boundaries, build → repair → verify yields no errors.

    This is the strongest correctness claim in the project (§11.3).
    """
    # Filter to values within [0, duration] and deduplicate
    boundaries = sorted({b for b in raw_boundaries if 0.0 <= b <= duration})
    assume(len(boundaries) >= 3)

    units = _make_units(duration)
    chapters = build_chapters("vid", boundaries, units, duration)
    assume(len(chapters) >= 1)

    repaired, report = repair_chapters(chapters, duration, units)
    assert report.repaired

    error_issues = [i for i in report.issues if i.severity == "error"]
    # R9 too-few is the one case repair cannot fix
    non_r9_errors = [i for i in error_issues if i.rule != "R9_count_range"]
    assert non_r9_errors == [], f"Unexpected errors after repair: {non_r9_errors}"
