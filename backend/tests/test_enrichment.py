"""Tests for agents/enrichment.py (§10.6)."""

import pytest
from app.agents.enrichment import enrich
from app.core.llm import LLMConfig
from app.core.wikipedia import WikiSummary
from app.schemas.enrichment import BlurbDraft, EnrichmentDrafts, Entity


def _entity(name: str, first_mention: float, needs: bool = True) -> Entity:
    return Entity(name=name, kind="concept", first_mention=first_mention, needs_enrichment=needs)


@pytest.mark.asyncio
async def test_skipped_when_no_entity_needs_enrichment() -> None:
    entities = [_entity("Google", 0.0, needs=False)]
    result = await enrich(entities, LLMConfig())
    assert result == []


@pytest.mark.asyncio
async def test_disabled_when_search_provider_none(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.agents.enrichment as mod

    monkeypatch.setattr(mod.settings, "SEARCH_PROVIDER", "none")
    result = await enrich([_entity("Kullback-Leibler divergence", 0.0)], LLMConfig())
    assert result == []


@pytest.mark.asyncio
async def test_wikipedia_hit_produces_note_with_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.agents.enrichment as mod

    async def fake_fetch(name: str) -> WikiSummary:
        return WikiSummary(
            title=name,
            extract="A measure of how one probability distribution differs from another.",
            url="https://en.wikipedia.org/wiki/Kullback-Leibler_divergence",
        )

    async def fake_llm(prompt, cfg, schema):
        return EnrichmentDrafts(
            notes=[
                BlurbDraft(
                    entity="Kullback-Leibler divergence", blurb="A distance between distributions."
                )
            ]
        )

    monkeypatch.setattr(mod, "fetch_summary", fake_fetch)
    monkeypatch.setattr(mod, "generate_structured", fake_llm)

    result = await enrich([_entity("Kullback-Leibler divergence", 42.0)], LLMConfig())

    assert len(result) == 1
    note = result[0]
    assert note.entity == "Kullback-Leibler divergence"
    assert note.blurb == "A distance between distributions."
    assert note.source_url == "https://en.wikipedia.org/wiki/Kullback-Leibler_divergence"
    assert note.first_mention == 42.0


@pytest.mark.asyncio
async def test_wikipedia_miss_falls_back_to_llm_without_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.agents.enrichment as mod

    async def fake_fetch(name: str) -> None:
        return None  # 404 / disambiguation

    async def fake_llm(prompt, cfg, schema):
        return EnrichmentDrafts(notes=[BlurbDraft(entity="Obscurium", blurb="A made-up concept.")])

    monkeypatch.setattr(mod, "fetch_summary", fake_fetch)
    monkeypatch.setattr(mod, "generate_structured", fake_llm)

    result = await enrich([_entity("Obscurium", 5.0)], LLMConfig())

    assert len(result) == 1
    assert result[0].blurb == "A made-up concept."
    assert result[0].source_url is None


@pytest.mark.asyncio
async def test_caps_at_max_enrichments_by_earliest_mention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.agents.enrichment as mod

    fetched_names: list[str] = []

    async def fake_fetch(name: str) -> WikiSummary:
        fetched_names.append(name)
        return WikiSummary(title=name, extract=f"About {name}.", url=f"https://x/{name}")

    async def fake_llm(prompt, cfg, schema):
        # Echo one blurb per entity block; entity names are in the prompt.
        return EnrichmentDrafts(
            notes=[BlurbDraft(entity=n, blurb=f"{n} blurb") for n in fetched_names]
        )

    monkeypatch.setattr(mod, "fetch_summary", fake_fetch)
    monkeypatch.setattr(mod, "generate_structured", fake_llm)

    # 8 candidates, out of order; only the 6 earliest should be fetched.
    entities = [_entity(f"E{i}", float(100 - i * 10)) for i in range(8)]
    result = await enrich(entities, LLMConfig())

    assert len(result) == mod.MAX_ENRICHMENTS == 6
    # Results are sorted by first_mention ascending.
    mentions = [n.first_mention for n in result]
    assert mentions == sorted(mentions)
    # The two latest-mentioned entities (E0=100s, E1=90s) are dropped.
    assert "E0" not in fetched_names and "E1" not in fetched_names
