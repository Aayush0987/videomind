"""Retrieval grading agent: judges whether retrieved chunks sufficiently
answer the question (§13).

With no cross-encoder reranker in V1 (§25.2), the grader is the precision layer.
Its prompt does two distinct jobs (§13.2): per-chunk relevance (is this passage
about the question?) and set-level sufficiency (do these, together, contain
enough to answer it?). The downstream router keeps only chunks scored at or
above ``RELEVANCE_THRESHOLD`` and requires the set to be marked sufficient.
"""

from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.schemas.qa import GradingOutput


def _render_chunks(chunks: list[dict]) -> str:
    blocks = []
    for chunk in chunks:
        blocks.append(f"[chunk_id={chunk['chunk_id']}]\n{chunk['document']}")
    return "\n\n".join(blocks)


async def grade_chunks(
    question: str,
    chunks: list[dict],
    llm_config: LLMConfig,
) -> GradingOutput:
    """Grade each chunk for relevance and the set for sufficiency (§13.2)."""
    template = load_prompt("grader")
    prompt = template.format(question=question, chunks=_render_chunks(chunks))
    return await generate_structured(prompt, llm_config, GradingOutput)
