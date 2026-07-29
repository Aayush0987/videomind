"""Tests for agents/entities.py (§10.6)."""

import pytest
from app.agents.entities import extract_entities
from app.core.llm import LLMConfig
from app.schemas.chapters import Chapter
from app.schemas.enrichment import Entity, EntityExtraction

from fakes.fake_llm import FakeLLM


def _chapter(idx: int, start: float, title: str, summary: str) -> Chapter:
    return Chapter(
        chapter_id=f"vid:ch{idx:02d}",
        idx=idx,
        start=start,
        end=start + 60,
        title=title,
        summary=summary,
    )


@pytest.mark.asyncio
async def test_extract_entities_runs_on_summaries(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agents.entities as emod

    chapters = [
        _chapter(0, 0.0, "Intro", "We meet Ada Lovelace."),
        _chapter(1, 120.0, "The Engine", "The Analytical Engine is described."),
    ]

    fake = FakeLLM()
    fake.responses["EntityExtraction"] = EntityExtraction(
        entities=[
            Entity(name="Ada Lovelace", kind="person", first_mention=0.0, needs_enrichment=False),
            Entity(
                name="Analytical Engine",
                kind="technology",
                first_mention=120.0,
                needs_enrichment=True,
            ),
        ]
    )
    monkeypatch.setattr(emod, "generate_structured", fake.generate_structured)

    result = await extract_entities(chapters, LLMConfig())

    assert len(result.entities) == 2
    # The prompt is built from the chapter summaries, with each chapter's start
    # second exposed so the model can attribute first_mention.
    prompt = fake.call_log[0].prompt
    assert "Ada Lovelace" in prompt
    assert "[120s]" in prompt
