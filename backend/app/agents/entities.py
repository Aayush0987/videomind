"""Entity extraction agent: identifies entities per chapter that may need
enrichment (§10.6).

Runs on the concatenated chapter summaries (not the raw transcript — cheaper and
less noisy). Returns an ``EntityExtraction`` capped at ``MAX_ENTITIES``.
"""

import logging

from app.config import MAX_ENTITIES
from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.schemas.chapters import Chapter
from app.schemas.enrichment import EntityExtraction

logger = logging.getLogger(__name__)


def _render_summaries(chapters: list[Chapter]) -> str:
    lines = []
    for ch in chapters:
        lines.append(f"[{int(ch.start)}s] {ch.title}: {ch.summary}")
    return "\n".join(lines)


async def extract_entities(chapters: list[Chapter], llm_config: LLMConfig) -> EntityExtraction:
    template = load_prompt("entities")
    prompt = template.format(max_entities=MAX_ENTITIES, summaries=_render_summaries(chapters))
    return await generate_structured(prompt, llm_config, EntityExtraction)
