"""Tests for agents/titling.py (§10.5, Phase 5 DoD).

The headline guarantee: batching keeps LLM cost flat — 20 chapters cost 4
titling calls, not 20.
"""

import pytest
from app.agents.titling import title_and_summarize
from app.core.llm import LLMConfig
from app.schemas.chapters import Chapter, ChapterCard, TitlingOutput
from app.schemas.transcript import SentenceUnit

from fakes.fake_llm import FakeLLM

_SUMMARY = "A" * 25  # satisfies ChapterCard.summary min_length=20


def _chapters(n: int) -> list[Chapter]:
    return [
        Chapter(chapter_id=f"vid:ch{i:02d}", idx=i, start=float(i * 60), end=float(i * 60 + 60))
        for i in range(n)
    ]


def _units(n_chapters: int) -> list[SentenceUnit]:
    units: list[SentenceUnit] = []
    idx = 0
    for i in range(n_chapters):
        for j in range(3):
            start = float(i * 60 + j * 20)
            units.append(
                SentenceUnit(idx=idx, start=start, end=start + 20, text=f"chapter {i} sentence {j}")
            )
            idx += 1
    return units


def _card(idx: int, title: str = "") -> ChapterCard:
    return ChapterCard(
        idx=idx,
        title=title or f"Distinct Topic {idx}",
        summary=_SUMMARY,
        key_points=["point one", "point two"],
    )


def _titling_calls(fake: FakeLLM) -> list:
    return [c for c in fake.call_log if c.schema is TitlingOutput]


# ---------------------------------------------------------------------------
# The headline batching assertion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_20_chapters_produce_4_titling_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agents.titling as tmod

    chapters = _chapters(20)
    units = _units(20)

    fake = FakeLLM()
    # A single canned response covering all 20 indices. Every batch resolves by
    # schema name and filters down to its requested indices — a superset never
    # triggers the missing-index re-ask.
    fake.responses["TitlingOutput"] = TitlingOutput(cards=[_card(i) for i in range(20)])
    monkeypatch.setattr(tmod, "generate_structured", fake.generate_structured)

    result = await title_and_summarize(chapters, units, LLMConfig(), video_title="Test")

    # TITLING_BATCH_SIZE = 6 → batches [0-5][6-11][12-17][18-19] = 4 calls, not 20.
    assert len(_titling_calls(fake)) == 4
    assert all(ch.title for ch in result)
    assert all(len(ch.key_points) >= 2 for ch in result)


# ---------------------------------------------------------------------------
# Post-checks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_banned_prefix_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agents.titling as tmod

    chapters = _chapters(2)
    units = _units(2)

    fake = FakeLLM()
    fake.responses["TitlingOutput"] = TitlingOutput(
        cards=[
            _card(0, title="Introduction to Back-propagation"),
            _card(1, title="Chapter: Gradient Descent"),
        ]
    )
    monkeypatch.setattr(tmod, "generate_structured", fake.generate_structured)

    result = await title_and_summarize(chapters, units, LLMConfig())

    assert result[0].title == "Back-propagation"
    assert result[1].title == "Gradient Descent"


@pytest.mark.asyncio
async def test_duplicate_titles_are_disambiguated(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agents.titling as tmod

    chapters = _chapters(2)
    units = _units(2)

    fake = FakeLLM()
    fake.responses["TitlingOutput"] = TitlingOutput(
        cards=[_card(0, title="Neural Nets"), _card(1, title="neural nets")]
    )
    monkeypatch.setattr(tmod, "generate_structured", fake.generate_structured)

    result = await title_and_summarize(chapters, units, LLMConfig())

    titles = {ch.title.casefold() for ch in result}
    assert len(titles) == 2, f"titles collided after casefold: {[c.title for c in result]}"


@pytest.mark.asyncio
async def test_missing_index_triggers_one_reask(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agents.titling as tmod

    chapters = _chapters(3)
    units = _units(3)

    fake = FakeLLM()
    # Response omits idx 2 → exactly one re-ask for the missing index.
    fake.responses["TitlingOutput"] = TitlingOutput(cards=[_card(0), _card(1)])
    monkeypatch.setattr(tmod, "generate_structured", fake.generate_structured)

    result = await title_and_summarize(chapters, units, LLMConfig())

    assert len(_titling_calls(fake)) == 2  # initial batch + one re-ask
    assert result[0].title and result[1].title
    assert result[2].title == ""  # still skipped, left untitled rather than crashing
