"""Answer generation agent: produces the final cited answer from retrieved chunks (§13).

The model answers only from the supplied chunks and cites by ``chunk_id`` plus a
short quote — it never supplies timestamps. Deterministic code (§13.5) resolves
each cited chunk's real time range afterwards, which makes a hallucinated
timestamp structurally impossible.
"""

from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.schemas.qa import AnswerDraft


def _mmss(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def _chunk_text(chunk: dict) -> str:
    # doc_text is "chapter_title\ntext"; strip the title line for display.
    document = chunk["document"]
    return document.split("\n", 1)[1] if "\n" in document else document


def _render_chunks(chunks: list[dict]) -> str:
    blocks = []
    for chunk in chunks:
        meta = chunk["metadata"]
        header = (
            f"[chunk_id={chunk['chunk_id']} | "
            f"{_mmss(meta['start'])}–{_mmss(meta['end'])} | "
            f'Chapter: "{meta["chapter_title"]}"]'
        )
        blocks.append(f"{header} {_chunk_text(chunk)}")
    return "\n\n".join(blocks)


def _render_history(history: list[dict]) -> str:
    if not history:
        return "(no prior turns)"
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)


async def answer(
    question: str,
    history: list[dict],
    chunks: list[dict],
    llm_config: LLMConfig,
) -> AnswerDraft:
    """Draft a cited answer grounded only in ``chunks`` (§13.4)."""
    template = load_prompt("answerer")
    prompt = template.format(
        question=question,
        history=_render_history(history),
        chunks=_render_chunks(chunks),
    )
    return await generate_structured(prompt, llm_config, AnswerDraft)
