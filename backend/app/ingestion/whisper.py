"""Local faster-whisper fallback transcription, rung 4 of §9.3.

Skipped entirely when `ENABLE_WHISPER=false`.
"""

import tempfile
from pathlib import Path

import yt_dlp
from faster_whisper import WhisperModel

from app.config import settings
from app.schemas.transcript import TranscriptCue


def transcribe(video_id: str, url: str) -> tuple[list[TranscriptCue], str]:
    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path = _download_audio(video_id, url, tmp_dir)
        model = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(audio_path))
        cues = [
            TranscriptCue(start=segment.start, end=segment.end, text=segment.text)
            for segment in segments
        ]
        return cues, info.language


def _download_audio(video_id: str, url: str, tmp_dir: str) -> Path:
    ydl_opts: dict[str, object] = {
        "format": "bestaudio",
        "skip_download": False,
        "quiet": True,
        "no_warnings": True,
        "outtmpl": str(Path(tmp_dir) / f"{video_id}.%(ext)s"),
    }
    if settings.YTDLP_COOKIES_FILE:
        ydl_opts["cookiefile"] = settings.YTDLP_COOKIES_FILE
    if settings.YTDLP_PROXY:
        ydl_opts["proxy"] = settings.YTDLP_PROXY

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    audio_files = [p for p in Path(tmp_dir).glob(f"{video_id}.*")]
    return audio_files[0]
