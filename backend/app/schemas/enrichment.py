"""Pydantic models for extracted entities and enrichment results (§6, §10.6)."""

from typing import Literal

from pydantic import BaseModel, Field

# --- Extracted entities (LLM output of the entity agent) ---


class Entity(BaseModel):
    name: str = Field(max_length=80)
    kind: Literal["person", "organization", "technology", "concept", "place", "event", "product"]
    first_mention: float
    needs_enrichment: bool


class EntityExtraction(BaseModel):
    entities: list[Entity] = Field(max_length=15)


# --- Enrichment result (attached to the analysis, not raw LLM output) ---


class EnrichmentNote(BaseModel):
    entity: str
    kind: str
    blurb: str = Field(max_length=300)
    source_url: str | None = None
    first_mention: float


# --- Thin LLM-output plumbing for the enrichment agent's condense/fallback
# calls. The full EnrichmentNote is assembled in Python from known entity
# metadata (kind, first_mention) and the fetched source URL, so the model only
# has to write prose. Mirrors the SegmentationOutput/TitlingOutput pattern. ---


class BlurbDraft(BaseModel):
    entity: str = Field(max_length=80)
    blurb: str = Field(max_length=300)


class EnrichmentDrafts(BaseModel):
    notes: list[BlurbDraft]
