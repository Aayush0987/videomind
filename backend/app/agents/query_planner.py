"""Q&A query planning agent: expands a user question into retrieval sub-queries (§13).

The escalation ladder (§13.3) is deterministic: the calling graph passes the
current attempt index and this agent picks the strategy and ``top_k`` from
``RETRIEVAL_ESCALATION`` — not the model. The LLM does only the linguistic work
(resolve references, decompose, write a HyDE paragraph, or extract keywords),
and its emitted ``strategy``/``top_k`` are overwritten so a mis-behaving model
can never break the ladder that makes each retry genuinely different.
"""

from app.config import RETRIEVAL_ESCALATION
from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.schemas.qa import QueryPlan

_STRATEGY_INSTRUCTIONS = {
    "direct": (
        "Resolve any pronouns or references against the conversation history and "
        "lightly rewrite the question into one self-contained search query. Put it "
        "in `rewritten_query` and leave `sub_queries` empty."
    ),
    "decompose": (
        "The first retrieval was insufficient. Split the question into up to 3 "
        "focused, standalone sub-questions that together cover it, and put them in "
        "`sub_queries`. Also give a single combined query in `rewritten_query`."
    ),
    "hyde": (
        "The first retrieval was insufficient. Write a short hypothetical answer "
        "paragraph as it might appear spoken in the transcript, and put THAT text "
        "in `rewritten_query` (we embed the hypothetical answer, not the question). "
        "Leave `sub_queries` empty."
    ),
    "keyword": (
        "Earlier retrievals were insufficient. Extract the salient nouns and proper "
        "nouns from the question as a keyword bag and put the space-joined keywords "
        "in `rewritten_query`. Leave `sub_queries` empty."
    ),
}

_MAX_ATTEMPT = max(RETRIEVAL_ESCALATION)


def _render_history(history: list[dict]) -> str:
    if not history:
        return "(no prior turns)"
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in history)


async def plan_query(
    question: str,
    history: list[dict],
    attempt: int,
    llm_config: LLMConfig,
    *,
    missing_information: str | None = None,
) -> QueryPlan:
    """Plan retrieval for one pass, escalating strategy by ``attempt`` (§13.3)."""
    strategy, top_k = RETRIEVAL_ESCALATION[min(attempt, _MAX_ATTEMPT)]
    template = load_prompt("query_planner")
    prompt = template.format(
        question=question,
        history=_render_history(history),
        strategy=strategy,
        top_k=top_k,
        strategy_instructions=_STRATEGY_INSTRUCTIONS[strategy],
        missing_information=missing_information or "(none — this is the first attempt)",
    )
    plan = await generate_structured(prompt, llm_config, QueryPlan)
    # Enforce the deterministic ladder regardless of what the model emitted.
    return plan.model_copy(update={"strategy": strategy, "top_k": top_k})
