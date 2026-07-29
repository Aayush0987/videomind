"""`AnalysisState` and `QAState` TypedDicts for LangGraph partial-update
semantics (§3, §10, §13).
"""

from typing import TypedDict

from app.core.llm import LLMConfig
from app.schemas.chapters import Chapter, VerificationReport
from app.schemas.enrichment import EnrichmentNote, Entity
from app.schemas.transcript import Transcript


class AnalysisState(TypedDict, total=False):
    # inputs
    job_id: str
    url: str
    video_id: str
    llm: LLMConfig
    # accumulated
    metadata: dict
    transcript: Transcript
    unit_embeddings: list[list[float]]
    boundaries: list[float]
    chapters: list[Chapter]
    verification: VerificationReport
    entities: list[Entity]
    enrichment: list[EnrichmentNote]
    # control
    segmentation_attempts: int
    stage: str
    errors: list[str]
