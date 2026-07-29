"""Chapter titling and summarization agent, batched across chapters (§10.5).

One LLM call per batch of ``TITLING_BATCH_SIZE`` chapters keeps token cost flat
for long videos: 20 chapters cost 4 calls, not 20. Deterministic post-checks
enforce index coverage, title uniqueness, and banned-prefix specificity.
"""

import logging

from app.config import (
    BANNED_TITLE_PREFIXES,
    TITLING_BATCH_SIZE,
    TITLING_CHAR_BUDGET,
)
from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.schemas.chapters import Chapter, ChapterCard, TitlingOutput
from app.schemas.transcript import SentenceUnit

logger = logging.getLogger(__name__)


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _truncate_head_tail(text: str, budget: int) -> str:
    """Keep the head (70%) and tail (30%) — the end of a segment often carries
    the conclusion."""
    if len(text) <= budget:
        return text
    head_len = int(budget * 0.7)
    tail_len = budget - head_len
    return f"{text[:head_len]} … {text[-tail_len:]}"


def _chapter_text(chapter: Chapter, units: list[SentenceUnit]) -> str:
    parts = [u.text for u in units if chapter.start <= u.start < chapter.end]
    return _truncate_head_tail(" ".join(parts), TITLING_CHAR_BUDGET)


def _render_batch(batch: list[Chapter], units: list[SentenceUnit]) -> str:
    blocks = []
    for ch in batch:
        header = f"### Chapter {ch.idx} ({_mmss(ch.start)}–{_mmss(ch.end)})"
        blocks.append(f"{header}\n{_chapter_text(ch, units)}")
    return "\n\n".join(blocks)


def _strip_banned_prefix(title: str) -> str:
    lowered = title.casefold()
    for prefix in BANNED_TITLE_PREFIXES:
        if lowered.startswith(prefix):
            stripped = title[len(prefix) :].lstrip(" :–—-").strip()
            if len(stripped) >= 3:
                return stripped
    return title


def _disambiguate(title: str, seen: set[str]) -> str:
    base = title
    key = base.casefold()
    n = 2
    while key in seen:
        title = f"{base} ({n})"
        key = title.casefold()
        n += 1
    seen.add(key)
    return title


async def _title_batch(
    template: str,
    batch: list[Chapter],
    units: list[SentenceUnit],
    llm_config: LLMConfig,
    video_title: str,
) -> dict[int, ChapterCard]:
    requested = {ch.idx for ch in batch}
    prompt = template.format(video_title=video_title, chapters=_render_batch(batch, units))
    output = await generate_structured(prompt, llm_config, TitlingOutput)
    cards = {c.idx: c for c in output.cards if c.idx in requested}

    missing = requested - cards.keys()
    if missing:  # one re-ask for just the indices the model skipped
        retry_batch = [ch for ch in batch if ch.idx in missing]
        retry_prompt = template.format(
            video_title=video_title, chapters=_render_batch(retry_batch, units)
        )
        retry = await generate_structured(retry_prompt, llm_config, TitlingOutput)
        for c in retry.cards:
            if c.idx in missing:
                cards[c.idx] = c
    return cards


def _apply(chapters: list[Chapter], cards: dict[int, ChapterCard]) -> list[Chapter]:
    seen: set[str] = set()
    result: list[Chapter] = []
    for ch in chapters:
        card = cards.get(ch.idx)
        if card is None:  # model skipped it even after the re-ask; leave untitled
            result.append(ch)
            continue
        title = _disambiguate(_strip_banned_prefix(card.title), seen)
        result.append(
            ch.model_copy(
                update={
                    "title": title,
                    "summary": card.summary,
                    "key_points": card.key_points,
                }
            )
        )
    return result


async def title_and_summarize(
    chapters: list[Chapter],
    units: list[SentenceUnit],
    llm_config: LLMConfig,
    *,
    video_title: str = "",
) -> list[Chapter]:
    """Title and summarize every chapter, one LLM call per batch of
    ``TITLING_BATCH_SIZE``."""
    template = load_prompt("titling")
    cards: dict[int, ChapterCard] = {}
    for i in range(0, len(chapters), TITLING_BATCH_SIZE):
        batch = chapters[i : i + TITLING_BATCH_SIZE]
        cards.update(await _title_batch(template, batch, units, llm_config, video_title))
    return _apply(chapters, cards)
