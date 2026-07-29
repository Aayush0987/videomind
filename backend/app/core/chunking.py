"""Chunking logic (§12.1). Builds chunks from SentenceUnits, never raw characters.

Chunks respect chapter boundaries, apply greedy accumulation up to
CHUNK_MAX_CHARS, and overlap by CHUNK_OVERLAP_UNITS.
"""

from dataclasses import dataclass

from app.config import CHUNK_MAX_CHARS, CHUNK_OVERLAP_UNITS
from app.schemas.transcript import SentenceUnit


@dataclass
class ChapterRange:
    """Minimal chapter descriptor for chunking. Phase 4 produces these."""

    chapter_id: str
    chapter_idx: int
    chapter_title: str
    start: float
    end: float


@dataclass
class Chunk:
    chunk_id: str
    video_id: str
    chapter_id: str
    chapter_idx: int
    chapter_title: str
    start: float
    end: float
    unit_start_idx: int
    unit_end_idx: int
    text: str
    doc_text: str


def build_chunks(
    video_id: str,
    units: list[SentenceUnit],
    chapters: list[ChapterRange],
) -> list[Chunk]:
    """Greedily chunk units within each chapter, with overlap."""
    chunks: list[Chunk] = []
    global_idx = 0

    for chapter in chapters:
        chapter_units = [u for u in units if u.start >= chapter.start and u.start < chapter.end]
        if not chapter_units:
            continue

        buf: list[SentenceUnit] = []
        buf_chars = 0

        for unit in chapter_units:
            unit_len = len(unit.text)

            if buf and buf_chars + 1 + unit_len > CHUNK_MAX_CHARS:
                chunks.append(_emit_chunk(video_id, global_idx, chapter, buf))
                global_idx += 1
                overlap = buf[-CHUNK_OVERLAP_UNITS:]
                buf = list(overlap)
                buf_chars = sum(len(u.text) for u in buf)

            buf.append(unit)
            buf_chars += (1 if buf_chars > 0 else 0) + unit_len

        if buf:
            chunks.append(_emit_chunk(video_id, global_idx, chapter, buf))
            global_idx += 1

    return chunks


def _emit_chunk(
    video_id: str,
    index: int,
    chapter: ChapterRange,
    buf: list[SentenceUnit],
) -> Chunk:
    text = " ".join(u.text for u in buf)
    return Chunk(
        chunk_id=f"{video_id}:c{index:04d}",
        video_id=video_id,
        chapter_id=chapter.chapter_id,
        chapter_idx=chapter.chapter_idx,
        chapter_title=chapter.chapter_title,
        start=buf[0].start,
        end=buf[-1].end,
        unit_start_idx=buf[0].idx,
        unit_end_idx=buf[-1].idx,
        text=text,
        doc_text=f"{chapter.chapter_title}\n{text}",
    )
