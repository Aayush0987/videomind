"""Pydantic models for chapters, `SegmentationOutput`, and `VerificationReport` (§6, §11)."""

from typing import Literal

from pydantic import BaseModel, Field

# --- LLM output: segmentation agent ---


class ProposedBoundary(BaseModel):
    start: float = Field(ge=0, description="Second at which a new topic begins")
    reason: str = Field(max_length=160, description="Why the topic shifts here")


class SegmentationOutput(BaseModel):
    boundaries: list[ProposedBoundary]


# --- LLM output: titling agent (one call per batch of chapters) ---


class ChapterCard(BaseModel):
    idx: int
    title: str = Field(min_length=3, max_length=80)
    summary: str = Field(min_length=20, max_length=400)
    key_points: list[str] = Field(min_length=2, max_length=4)


class TitlingOutput(BaseModel):
    cards: list[ChapterCard]


# --- Internal, post-verification ---


class Chapter(BaseModel):
    chapter_id: str
    idx: int
    start: float
    end: float
    title: str = ""
    summary: str = ""
    key_points: list[str] = []


# --- Verification report (deterministic) ---


class VerificationIssue(BaseModel):
    rule: str
    severity: Literal["error", "warning"]
    detail: str
    chapter_idx: int | None = None


class VerificationReport(BaseModel):
    valid: bool
    issues: list[VerificationIssue]
    repaired: bool = False
