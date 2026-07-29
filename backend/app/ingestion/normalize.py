"""Deterministic cues -> sentence units normalization, no LLM involved (§9.4)."""

import re

from app.config import UNIT_MAX_CHARS, UNIT_MAX_SECONDS
from app.schemas.transcript import SentenceUnit, TranscriptCue

_BRACKET_RE = re.compile(r"\[[^\]]*\]")
_SPEAKER_MARKER_RE = re.compile(r">+")
_WHITESPACE_RE = re.compile(r"\s+")
_SENTENCE_END_CHARS = (".", "?", "!")

# Minimum word-overlap before two consecutive cues are treated as a rolling
# auto-caption duplicate rather than a coincidental shared word.
_MIN_DEDUPE_OVERLAP_WORDS = 2


def normalize(cues: list[TranscriptCue]) -> list[SentenceUnit]:
    cleaned = _clean_and_dedupe(cues)
    return _accumulate(cleaned)


def _clean_and_dedupe(cues: list[TranscriptCue]) -> list[TranscriptCue]:
    ordered = sorted(cues, key=lambda cue: cue.start)
    result: list[TranscriptCue] = []
    prev_words: list[str] = []
    for cue in ordered:
        end = max(cue.end, cue.start + 0.5)
        text = _strip_markers(cue.text)
        text = _WHITESPACE_RE.sub(" ", text).strip()
        if not text:
            continue
        words = text.split(" ")
        new_words = _dedupe_suffix(prev_words, words)
        prev_words = words
        if not new_words:
            continue
        result.append(TranscriptCue(start=cue.start, end=end, text=" ".join(new_words)))
    return result


def _strip_markers(text: str) -> str:
    text = _BRACKET_RE.sub(" ", text)
    return _SPEAKER_MARKER_RE.sub(" ", text)


def _dedupe_suffix(prev_words: list[str], words: list[str]) -> list[str]:
    max_overlap = min(len(prev_words), len(words))
    for overlap in range(max_overlap, _MIN_DEDUPE_OVERLAP_WORDS - 1, -1):
        if prev_words[-overlap:] == words[:overlap]:
            return words[overlap:]
    return words


def _accumulate(cues: list[TranscriptCue]) -> list[SentenceUnit]:
    units: list[SentenceUnit] = []
    buf_words: list[str] = []
    buf_start = 0.0
    buf_end = 0.0

    for cue in cues:
        if not buf_words:
            buf_start = cue.start
        buf_words.extend(cue.text.split(" "))
        buf_end = cue.end

        ends_sentence = cue.text.rstrip()[-1:] in _SENTENCE_END_CHARS
        duration = buf_end - buf_start
        length = len(" ".join(buf_words))
        if ends_sentence or duration >= UNIT_MAX_SECONDS or length >= UNIT_MAX_CHARS:
            units.append(
                SentenceUnit(idx=len(units), start=buf_start, end=buf_end, text=" ".join(buf_words))
            )
            buf_words = []

    if buf_words:
        units.append(
            SentenceUnit(idx=len(units), start=buf_start, end=buf_end, text=" ".join(buf_words))
        )

    return units
