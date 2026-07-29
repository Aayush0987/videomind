"""Entity enrichment agent: fetches Wikipedia context for entities flagged
`needs_enrichment` (§10.6).

Handles at most ``MAX_ENRICHMENTS`` entities, chosen by earliest first mention.
Each is looked up via the free, keyless Wikipedia REST summary; a 404 or
disambiguation page falls back to a single LLM blurb with ``source_url=None``.
One batched LLM call condenses all fetched extracts.
"""

import logging

from app.config import MAX_ENRICHMENTS, settings
from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.core.wikipedia import fetch_summary
from app.schemas.enrichment import EnrichmentDrafts, EnrichmentNote, Entity

logger = logging.getLogger(__name__)


async def enrich(entities: list[Entity], llm_config: LLMConfig) -> list[EnrichmentNote]:
    if settings.SEARCH_PROVIDER == "none":
        return []

    targets = sorted((e for e in entities if e.needs_enrichment), key=lambda e: e.first_mention)[
        :MAX_ENRICHMENTS
    ]
    if not targets:
        return []

    fetched: list[tuple[Entity, str, str]] = []  # (entity, extract, source_url)
    failed: list[Entity] = []
    for ent in targets:
        summary = await fetch_summary(ent.name)
        if summary is None:
            failed.append(ent)
        else:
            fetched.append((ent, summary.extract, summary.url))

    notes: list[EnrichmentNote] = []
    if fetched:
        notes.extend(await _condense(fetched, llm_config))
    for ent in failed:
        notes.append(await _fallback(ent, llm_config))

    notes.sort(key=lambda n: n.first_mention)
    return notes


async def _condense(
    fetched: list[tuple[Entity, str, str]], llm_config: LLMConfig
) -> list[EnrichmentNote]:
    template = load_prompt("enrichment")
    blocks = [f"### {ent.name} ({ent.kind})\n{extract}" for ent, extract, _ in fetched]
    prompt = template.format(extracts="\n\n".join(blocks))
    drafts = await generate_structured(prompt, llm_config, EnrichmentDrafts)
    blurb_by_entity = {d.entity.casefold(): d.blurb for d in drafts.notes}

    notes: list[EnrichmentNote] = []
    for ent, extract, url in fetched:
        blurb = blurb_by_entity.get(ent.name.casefold(), extract[:300])
        notes.append(
            EnrichmentNote(
                entity=ent.name,
                kind=ent.kind,
                blurb=blurb,
                source_url=url,
                first_mention=ent.first_mention,
            )
        )
    return notes


async def _fallback(ent: Entity, llm_config: LLMConfig) -> EnrichmentNote:
    template = load_prompt("enrichment_fallback")
    prompt = template.format(entity=ent.name, kind=ent.kind)
    drafts = await generate_structured(prompt, llm_config, EnrichmentDrafts)
    blurb = drafts.notes[0].blurb if drafts.notes else ""
    return EnrichmentNote(
        entity=ent.name,
        kind=ent.kind,
        blurb=blurb,
        source_url=None,
        first_mention=ent.first_mention,
    )
