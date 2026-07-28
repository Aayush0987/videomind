"""Deterministic verification agent: validates and repairs chapter segmentation
against 12 rules (§11).

Must not import anything from `core/llm.py` — verification is rule-based,
not LLM-based, by design.
"""

from app.config import MIN_CHAPTER_SECONDS
from app.schemas.chapters import Chapter, VerificationIssue, VerificationReport
from app.schemas.transcript import SentenceUnit


def verify_chapters(
    chapters: list[Chapter],
    duration: float,
    units: list[SentenceUnit],
    *,
    after_titling: bool = False,
) -> VerificationReport:
    """Run R1–R12, return a report. R10/R11 are skipped before titling."""
    issues: list[VerificationIssue] = []

    if not chapters:
        issues.append(
            VerificationIssue(
                rule="R9_count_range",
                severity="error",
                detail="No chapters produced",
            )
        )
        return VerificationReport(valid=False, issues=issues)

    # R1: chapters strictly ordered by start
    for i in range(len(chapters) - 1):
        if chapters[i].start >= chapters[i + 1].start:
            issues.append(
                VerificationIssue(
                    rule="R1_sorted",
                    severity="error",
                    detail=(
                        f"Chapter {i} start={chapters[i].start} "
                        f">= chapter {i + 1} start={chapters[i + 1].start}"
                    ),
                    chapter_idx=i,
                )
            )

    # R2: first chapter starts at (or near) zero
    if chapters[0].start > 1.0:
        issues.append(
            VerificationIssue(
                rule="R2_starts_at_zero",
                severity="error",
                detail=f"First chapter starts at {chapters[0].start}, expected <= 1.0",
                chapter_idx=0,
            )
        )

    # R3: no gaps between consecutive chapters
    for i in range(len(chapters) - 1):
        gap = chapters[i + 1].start - chapters[i].end
        if gap > 1.0:
            issues.append(
                VerificationIssue(
                    rule="R3_no_gaps",
                    severity="error",
                    detail=(
                        f"Gap of {gap:.1f}s between chapter {i} "
                        f"end={chapters[i].end} and chapter {i + 1} "
                        f"start={chapters[i + 1].start}"
                    ),
                    chapter_idx=i,
                )
            )

    # R4: no overlap between consecutive chapters
    for i in range(len(chapters) - 1):
        if chapters[i].end > chapters[i + 1].start:
            issues.append(
                VerificationIssue(
                    rule="R4_no_overlap",
                    severity="error",
                    detail=(
                        f"Chapter {i} end={chapters[i].end} "
                        f"> chapter {i + 1} start={chapters[i + 1].start}"
                    ),
                    chapter_idx=i,
                )
            )

    # R5: last chapter covers the end of the video
    if chapters[-1].end < duration - 2.0:
        issues.append(
            VerificationIssue(
                rule="R5_covers_end",
                severity="error",
                detail=f"Last chapter ends at {chapters[-1].end}, duration is {duration}",
                chapter_idx=len(chapters) - 1,
            )
        )

    # R6: every start/end within [0, duration]
    for i, ch in enumerate(chapters):
        if ch.start < 0 or ch.end > duration:
            issues.append(
                VerificationIssue(
                    rule="R6_within_bounds",
                    severity="error",
                    detail=f"Chapter {i} [{ch.start}, {ch.end}] outside [0, {duration}]",
                    chapter_idx=i,
                )
            )

    # R7: minimum chapter duration
    for i, ch in enumerate(chapters):
        dur = ch.end - ch.start
        if dur < MIN_CHAPTER_SECONDS:
            issues.append(
                VerificationIssue(
                    rule="R7_min_duration",
                    severity="error",
                    detail=f"Chapter {i} duration {dur:.1f}s < {MIN_CHAPTER_SECONDS}s",
                    chapter_idx=i,
                )
            )

    # R8: maximum chapter duration (warning only)
    max_dur = max(900, 0.35 * duration)
    for i, ch in enumerate(chapters):
        dur = ch.end - ch.start
        if dur > max_dur:
            issues.append(
                VerificationIssue(
                    rule="R8_max_duration",
                    severity="warning",
                    detail=f"Chapter {i} duration {dur:.1f}s > {max_dur:.1f}s",
                    chapter_idx=i,
                )
            )

    # R9: chapter count in range
    n = len(chapters)
    max_by_duration = int(duration / MIN_CHAPTER_SECONDS)
    if n < 3:
        issues.append(
            VerificationIssue(
                rule="R9_count_range",
                severity="error",
                detail=f"Only {n} chapters, minimum is 3",
            )
        )
    elif n > 25:
        issues.append(
            VerificationIssue(
                rule="R9_count_range",
                severity="error",
                detail=f"{n} chapters exceeds maximum of 25",
            )
        )
    elif n > max_by_duration:
        issues.append(
            VerificationIssue(
                rule="R9_count_range",
                severity="error",
                detail=f"{n} chapters exceeds duration-based max of {max_by_duration}",
            )
        )

    # R10: title present, ≤80 chars, unique (only after titling)
    if after_titling:
        seen_titles: set[str] = set()
        for i, ch in enumerate(chapters):
            if not ch.title:
                issues.append(
                    VerificationIssue(
                        rule="R10_title_present",
                        severity="error",
                        detail=f"Chapter {i} has no title",
                        chapter_idx=i,
                    )
                )
            elif len(ch.title) > 80:
                issues.append(
                    VerificationIssue(
                        rule="R10_title_present",
                        severity="error",
                        detail=f"Chapter {i} title is {len(ch.title)} chars (max 80)",
                        chapter_idx=i,
                    )
                )
            folded = ch.title.casefold()
            if folded and folded in seen_titles:
                issues.append(
                    VerificationIssue(
                        rule="R10_title_present",
                        severity="error",
                        detail=f"Chapter {i} title '{ch.title}' is a duplicate",
                        chapter_idx=i,
                    )
                )
            if folded:
                seen_titles.add(folded)

    # R11: summary present, 2-4 key points (only after titling)
    if after_titling:
        for i, ch in enumerate(chapters):
            if not ch.summary:
                issues.append(
                    VerificationIssue(
                        rule="R11_summary_present",
                        severity="error",
                        detail=f"Chapter {i} has no summary",
                        chapter_idx=i,
                    )
                )
            kp_count = len(ch.key_points)
            if kp_count < 2 or kp_count > 4:
                issues.append(
                    VerificationIssue(
                        rule="R11_summary_present",
                        severity="error",
                        detail=f"Chapter {i} has {kp_count} key points (expected 2-4)",
                        chapter_idx=i,
                    )
                )

    # R12: boundary on a sentence unit
    unit_starts = {u.start for u in units}
    for i, ch in enumerate(chapters):
        if ch.start not in unit_starts and ch.start != 0.0:
            issues.append(
                VerificationIssue(
                    rule="R12_boundary_on_unit",
                    severity="warning",
                    detail=f"Chapter {i} start={ch.start} does not match any unit start",
                    chapter_idx=i,
                )
            )

    valid = not any(issue.severity == "error" for issue in issues)
    return VerificationReport(valid=valid, issues=issues)


def repair_chapters(
    chapters: list[Chapter],
    duration: float,
    units: list[SentenceUnit],
) -> tuple[list[Chapter], VerificationReport]:
    """Apply deterministic fixes in rule order, then re-verify.

    Returns the repaired chapter list and a verification report with
    ``repaired=True``.
    """
    if not chapters:
        report = verify_chapters(chapters, duration, units)
        report = report.model_copy(update={"repaired": True})
        return chapters, report

    video_id = chapters[0].chapter_id.split(":")[0]

    # Work on mutable copies
    chs = [ch.model_copy() for ch in chapters]

    # R1: sort by start
    chs.sort(key=lambda c: c.start)

    # R2: clamp first chapter start to 0
    if chs[0].start > 1.0:
        chs[0] = chs[0].model_copy(update={"start": 0.0})

    # R3 + R4: snap each chapter's end to next chapter's start
    for i in range(len(chs) - 1):
        chs[i] = chs[i].model_copy(update={"end": chs[i + 1].start})

    # R5: extend last chapter to duration
    chs[-1] = chs[-1].model_copy(update={"end": duration})

    # R6: clamp to [0, duration], drop empties
    clamped: list[Chapter] = []
    for ch in chs:
        start = max(0.0, ch.start)
        end = min(duration, ch.end)
        if start < end:
            clamped.append(ch.model_copy(update={"start": start, "end": end}))
    chs = clamped if clamped else chs[:1]

    # R7: merge too-short chapters into shorter neighbour
    chs = _merge_short_chapters(chs, MIN_CHAPTER_SECONDS)

    # R9: if too many, merge shortest iteratively
    max_count = min(25, int(duration / MIN_CHAPTER_SECONDS))
    while len(chs) > max_count and len(chs) > 1:
        shortest_idx = min(range(len(chs)), key=lambda i: chs[i].end - chs[i].start)
        chs = _merge_into_neighbour(chs, shortest_idx)

    # R10: truncate titles, disambiguate (non-empty only)
    for i, ch in enumerate(chs):
        if ch.title and len(ch.title) > 80:
            chs[i] = ch.model_copy(update={"title": ch.title[:80]})

    seen: dict[str, int] = {}
    for i, ch in enumerate(chs):
        if not ch.title:
            continue
        folded = ch.title.casefold()
        if folded in seen:
            seen[folded] += 1
            chs[i] = ch.model_copy(update={"title": f"{ch.title[:74]} ({seen[folded]})"})
        else:
            seen[folded] = 1

    # R12: snap start to nearest unit start
    if units:
        unit_starts = sorted({u.start for u in units})
        for i, ch in enumerate(chs):
            nearest = min(unit_starts, key=lambda s: abs(s - ch.start))
            if nearest != ch.start:
                chs[i] = ch.model_copy(update={"start": nearest})
        # Re-snap ends after snapping starts
        for i in range(len(chs) - 1):
            chs[i] = chs[i].model_copy(update={"end": chs[i + 1].start})
        chs[-1] = chs[-1].model_copy(update={"end": duration})

    # Re-index and regenerate chapter_ids
    for i in range(len(chs)):
        chs[i] = chs[i].model_copy(
            update={
                "idx": i,
                "chapter_id": f"{video_id}:ch{i:02d}",
            }
        )

    report = verify_chapters(chs, duration, units)
    report = report.model_copy(update={"repaired": True})
    return chs, report


def _merge_short_chapters(chapters: list[Chapter], min_dur: float) -> list[Chapter]:
    """Merge chapters shorter than *min_dur* into their shorter neighbour."""
    changed = True
    while changed:
        changed = False
        for i, ch in enumerate(chapters):
            if ch.end - ch.start < min_dur and len(chapters) > 1:
                chapters = _merge_into_neighbour(chapters, i)
                changed = True
                break
    return chapters


def _merge_into_neighbour(chapters: list[Chapter], idx: int) -> list[Chapter]:
    """Merge chapter at *idx* into whichever neighbour is shorter."""
    chs = list(chapters)
    if idx == 0:
        target = 1
    elif idx == len(chs) - 1:
        target = idx - 1
    else:
        prev_dur = chs[idx - 1].end - chs[idx - 1].start
        next_dur = chs[idx + 1].end - chs[idx + 1].start
        target = idx - 1 if prev_dur <= next_dur else idx + 1

    if target < idx:
        chs[target] = chs[target].model_copy(update={"end": chs[idx].end})
    else:
        chs[target] = chs[target].model_copy(update={"start": chs[idx].start})

    chs.pop(idx)
    return chs
