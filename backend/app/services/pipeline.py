"""Thin orchestration entry points wiring ingestion, the analysis graph, and
the Q&A graph together.
"""

from app.config import settings
from app.core.errors import TranscriptUnavailableError, VideoTooLongError
from app.ingestion import captions, normalize, whisper
from app.schemas.transcript import Transcript


def acquire_transcript(video_id: str, url: str, duration: float) -> Transcript:
    if duration > settings.MAX_VIDEO_DURATION:
        raise VideoTooLongError(
            f"Video {video_id!r} duration {duration}s exceeds the "
            f"{settings.MAX_VIDEO_DURATION}s limit."
        )

    result = captions.fetch_captions(video_id, url)
    source = "captions"
    if result is None and settings.ENABLE_WHISPER:
        result = whisper.transcribe(video_id, url)
        source = "whisper"
    if result is None:
        raise TranscriptUnavailableError(
            f"All transcript acquisition rungs failed for {video_id!r}."
        )

    cues, language = result
    units = normalize.normalize(cues)
    return Transcript(
        video_id=video_id, source=source, language=language, duration=duration, units=units
    )
