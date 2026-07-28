"""Topic-boundary segmentation agent: proposes chapter boundaries from unit
embeddings and LLM refinement (§10.4).

Hybrid approach: deterministic candidate detection, then LLM selection.
"""

import logging
import math

from app.config import (
    MAX_SEGMENTATION_WINDOWS,
    MIN_CHAPTER_SECONDS,
    SEGMENTATION_CHAR_BUDGET,
)
from app.core.llm import LLMConfig, generate_structured
from app.core.prompts import load_prompt
from app.schemas.chapters import Chapter, SegmentationOutput
from app.schemas.transcript import SentenceUnit

logger = logging.getLogger(__name__)

_W = 4  # window size for smoothed cosine distance


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na < 1e-12 or nb < 1e-12:
        return 0.0
    return dot / (na * nb)


def _mean_vec(vecs: list[list[float]]) -> list[float]:
    n = len(vecs)
    dim = len(vecs[0])
    return [sum(vecs[j][d] for j in range(n)) / n for d in range(dim)]


def detect_candidates(
    units: list[SentenceUnit],
    embeddings: list[list[float]],
    min_spacing: float = MIN_CHAPTER_SECONDS,
) -> list[float]:
    """Detect candidate topic boundaries from embedding shifts (no LLM).

    Returns a sorted list of timestamps (``unit.start`` values) where
    topic shifts are detected.
    """
    if len(units) < 2 * _W + 1:
        return []

    # Compute smoothed cosine distance at each boundary position
    distances: list[tuple[int, float]] = []
    for i in range(_W, len(units) - _W):
        trailing = _mean_vec(embeddings[i - _W : i])
        leading = _mean_vec(embeddings[i : i + _W])
        dist = 1.0 - _cosine_sim(trailing, leading)
        distances.append((i, dist))

    if not distances:
        return []

    # Find local maxima above mean + 0.8 * std
    dist_values = [d for _, d in distances]
    mean = sum(dist_values) / len(dist_values)
    variance = sum((d - mean) ** 2 for d in dist_values) / len(dist_values)
    std = math.sqrt(variance)
    threshold = mean + 0.8 * std

    peaks: list[tuple[int, float]] = []
    for j in range(len(distances)):
        idx, dist = distances[j]
        if dist < threshold:
            continue
        prev_dist = distances[j - 1][1] if j > 0 else -1.0
        next_dist = distances[j + 1][1] if j < len(distances) - 1 else -1.0
        if dist >= prev_dist and dist >= next_dist:
            peaks.append((idx, dist))

    # Enforce min_spacing: keep strongest peak in each window
    peaks.sort(key=lambda p: units[p[0]].start)
    filtered: list[tuple[int, float]] = []
    for idx, dist in peaks:
        ts = units[idx].start
        if filtered and ts - units[filtered[-1][0]].start < min_spacing:
            # Keep the stronger peak
            if dist > filtered[-1][1]:
                filtered[-1] = (idx, dist)
        else:
            filtered.append((idx, dist))

    return [units[idx].start for idx, _ in filtered]


def _format_timestamp(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"[{m:02d}:{s:02d}]"


def _render_transcript(
    units: list[SentenceUnit],
    candidates: list[float],
) -> str:
    """Render transcript as ``[mm:ss] text`` lines with ``>>>`` markers."""
    candidate_set = set(candidates)
    lines: list[str] = []
    for unit in units:
        if unit.start in candidate_set:
            lines.append(">>>")
        lines.append(f"{_format_timestamp(unit.start)} {unit.text}")
    return "\n".join(lines)


def _split_into_windows(
    units: list[SentenceUnit],
    candidates: list[float],
    char_budget: int,
) -> list[list[SentenceUnit]]:
    """Split units into overlapping windows that fit the char budget."""
    full_text = _render_transcript(units, candidates)
    if len(full_text) <= char_budget:
        return [units]

    # Estimate units per window
    avg_chars_per_unit = len(full_text) / len(units)
    units_per_window = max(1, int(char_budget / avg_chars_per_unit))
    overlap = max(1, units_per_window // 10)

    windows: list[list[SentenceUnit]] = []
    start = 0
    for _ in range(MAX_SEGMENTATION_WINDOWS):
        end = min(start + units_per_window, len(units))
        windows.append(units[start:end])
        if end >= len(units):
            break
        start = end - overlap

    return windows


async def propose_boundaries(
    transcript_units: list[SentenceUnit],
    embeddings: list[list[float]],
    llm_config: LLMConfig,
    *,
    title: str = "",
    duration: float = 0.0,
) -> list[float]:
    """Detect candidates, refine with LLM, return sorted boundary list."""
    candidates = detect_candidates(transcript_units, embeddings)
    target = max(3, min(20, round(duration / 240)))
    target_min = max(3, target - 2)
    target_max = min(20, target + 2)

    prompt_template = load_prompt("segmentation")
    duration_m, duration_s = divmod(int(duration), 60)
    duration_fmt = f"{duration_m}:{duration_s:02d}"

    windows = _split_into_windows(transcript_units, candidates, SEGMENTATION_CHAR_BUDGET)

    all_boundaries: list[float] = []

    for window_units in windows:
        rendered = _render_transcript(window_units, candidates)
        prompt = prompt_template.format(
            title=title,
            duration=duration,
            duration_fmt=duration_fmt,
            target_min=target_min,
            target_max=target_max,
            transcript=rendered,
        )
        result = await generate_structured(prompt, llm_config, SegmentationOutput)
        all_boundaries.extend(b.start for b in result.boundaries)

    # Sort and enforce MIN_CHAPTER_SECONDS spacing
    all_boundaries.sort()
    merged: list[float] = []
    for b in all_boundaries:
        if merged and b - merged[-1] < MIN_CHAPTER_SECONDS:
            continue
        merged.append(b)

    return merged


def build_chapters(
    video_id: str,
    boundaries: list[float],
    units: list[SentenceUnit],
    duration: float,
) -> list[Chapter]:
    """Convert boundary timestamps to Chapter objects (deterministic).

    Snaps boundaries to nearest unit start, prepends 0.0, assigns IDs.
    """
    if not units:
        return []

    unit_starts = sorted({u.start for u in units})

    # Snap boundaries to nearest unit start
    snapped = set()
    for b in boundaries:
        nearest = min(unit_starts, key=lambda s: abs(s - b))
        snapped.add(nearest)

    # Always include 0.0 as the first boundary
    snapped.add(0.0)
    sorted_bounds = sorted(snapped)

    chapters: list[Chapter] = []
    for i, start in enumerate(sorted_bounds):
        end = sorted_bounds[i + 1] if i + 1 < len(sorted_bounds) else duration
        chapters.append(
            Chapter(
                chapter_id=f"{video_id}:ch{i:02d}",
                idx=i,
                start=start,
                end=end,
            )
        )

    return chapters
