"""Pydantic models for Q&A: query plans, grading verdicts, and cited answers (§6, §13)."""

from typing import Literal

from pydantic import BaseModel, Field


class QueryPlan(BaseModel):
    rewritten_query: str
    sub_queries: list[str] = Field(max_length=3)
    strategy: Literal["direct", "decompose", "hyde", "keyword"]
    top_k: int = Field(ge=3, le=20)


class ChunkGrade(BaseModel):
    chunk_id: str
    relevant: bool
    score: float = Field(ge=0, le=1)


class GradingOutput(BaseModel):
    grades: list[ChunkGrade]
    sufficient: bool
    missing_information: str | None = None


class CitationRef(BaseModel):
    """What the LLM is allowed to produce. NO timestamps — it does not get to invent those."""

    chunk_id: str
    quote: str = Field(max_length=200)


class AnswerDraft(BaseModel):
    answer: str  # contains inline markers [[c0]], [[c1]] ...
    citations: list[CitationRef]
    confidence: Literal["high", "medium", "low"]


class Citation(BaseModel):
    """Final, server-resolved. Timestamps come from chunk metadata, never the LLM."""

    marker: str  # "c0"
    chunk_id: str
    start: float
    end: float
    quote: str
    chapter_title: str
