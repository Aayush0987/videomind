"""Tests for app.ingestion.normalize (§9.4). Verified against two fixtures:
`transcript_short.json` (clean punctuation) and `transcript_long.json`
(45 min of auto-caption-style cues with zero terminal punctuation and
rolling-overlap duplication -- the hard case)."""

import json
from pathlib import Path

from app.config import UNIT_MAX_CHARS, UNIT_MAX_SECONDS
from app.ingestion.normalize import normalize
from app.schemas.transcript import TranscriptCue

_FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_cues(name: str) -> list[TranscriptCue]:
    data = json.loads((_FIXTURES_DIR / name).read_text())
    return [TranscriptCue(**cue) for cue in data]


def test_short_fixture_units_end_on_sentence_punctuation() -> None:
    cues = _load_cues("transcript_short.json")
    units = normalize(cues)

    assert len(units) > 1
    for unit in units[:-1]:
        assert unit.text.rstrip()[-1] in (".", "?", "!")


def test_short_fixture_strips_brackets_and_speaker_markers() -> None:
    cues = _load_cues("transcript_short.json")
    units = normalize(cues)

    joined = " ".join(unit.text for unit in units)
    assert "[Music]" not in joined
    assert "[Applause]" not in joined
    assert ">>" not in joined


def test_short_fixture_units_are_sequentially_indexed_and_ordered() -> None:
    """Starts are monotonically non-decreasing; ends are *not* asserted
    non-overlapping here since the 0.5s minimum-duration clamp (§9.4 step 1)
    can push a short cue's end past the next cue's start."""
    cues = _load_cues("transcript_short.json")
    units = normalize(cues)

    for i, unit in enumerate(units):
        assert unit.idx == i
    for earlier, later in zip(units, units[1:], strict=False):
        assert earlier.start <= later.start


def test_short_fixture_collapses_whitespace() -> None:
    cues = _load_cues("transcript_short.json")
    units = normalize(cues)

    for unit in units:
        assert "  " not in unit.text
        assert unit.text == unit.text.strip()


def test_long_fixture_units_never_exceed_duration_or_char_limits() -> None:
    """Boundaries are checked *after* a cue is folded into the buffer, so a
    unit can overshoot the limit by at most one cue's worth of duration/text
    -- the fixture's cues are individually short (<= ~3 words, <= ~2.2s), so
    a generous fixed tolerance for that single-cue overshoot is used here."""
    cues = _load_cues("transcript_long.json")
    units = normalize(cues)

    assert len(units) > 1
    for unit in units:
        assert (unit.end - unit.start) <= UNIT_MAX_SECONDS + 5.0
        assert len(unit.text) <= UNIT_MAX_CHARS + 50

    avg_duration = sum(unit.end - unit.start for unit in units) / len(units)
    assert avg_duration > UNIT_MAX_SECONDS * 0.5


def test_long_fixture_has_no_terminal_punctuation_boundaries() -> None:
    """The long fixture has zero sentence-ending punctuation anywhere, so
    every unit boundary must come from the duration/char limits, not from
    the punctuation branch."""
    cues = _load_cues("transcript_long.json")
    for cue in cues:
        assert cue.text.rstrip()[-1:] not in (".", "?", "!")

    units = normalize(cues)
    assert len(units) > 1


def test_dedupe_collapses_rolling_overlap_cues() -> None:
    cues = [
        TranscriptCue(start=0.0, end=2.0, text="the quick brown fox"),
        TranscriptCue(start=2.0, end=4.0, text="brown fox jumps over"),
        TranscriptCue(start=4.0, end=6.0, text="jumps over the lazy dog."),
    ]
    units = normalize(cues)

    assert len(units) == 1
    assert units[0].text == "the quick brown fox jumps over the lazy dog."


def test_dedupe_does_not_collapse_single_coincidental_word() -> None:
    cues = [
        TranscriptCue(start=0.0, end=2.0, text="I really like the color blue."),
        TranscriptCue(start=2.0, end=4.0, text="blue is my favorite color too."),
    ]
    units = normalize(cues)

    joined = " ".join(unit.text for unit in units)
    assert joined.count("blue") == 2


def test_short_cue_end_is_clamped_to_minimum_duration() -> None:
    cues = [TranscriptCue(start=0.0, end=0.1, text="Hi.")]
    units = normalize(cues)

    assert units[0].end - units[0].start >= 0.5


def test_empty_cues_returns_empty_units() -> None:
    assert normalize([]) == []
