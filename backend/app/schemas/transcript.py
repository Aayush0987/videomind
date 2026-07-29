"""Pydantic models for raw cues and normalized `SentenceUnit`s (§6, §9.4)."""

from typing import Literal

from pydantic import BaseModel, Field


class TranscriptCue(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str


class SentenceUnit(BaseModel):
    """Post-normalization atom. Everything downstream indexes on these."""

    idx: int
    start: float
    end: float
    text: str


class Transcript(BaseModel):
    video_id: str
    source: Literal["captions", "whisper"]
    language: str
    duration: float
    units: list[SentenceUnit]
