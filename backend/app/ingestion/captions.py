"""Transcript acquisition ladder: youtube-transcript-api, then yt-dlp
subtitle extraction (§9.3, rungs 1-3).
"""

import http.cookiejar
import json
import logging
import tempfile
from pathlib import Path
from typing import Any

import requests
import yt_dlp
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi
from youtube_transcript_api.proxies import GenericProxyConfig
from yt_dlp.utils import DownloadError

from app.config import settings
from app.schemas.transcript import TranscriptCue

logger = logging.getLogger(__name__)


def fetch_captions(video_id: str, url: str) -> tuple[list[TranscriptCue], str] | None:
    """Rungs 1-3 of §9.3. Each rung is attempted once; a failure is logged
    with the rung name and the ladder moves down. Returns `None` if all
    three rungs fail, leaving rung 4 (whisper) to the caller.
    """
    for rung_name, rung in (("manual_captions", _fetch_manual), ("auto_captions", _fetch_auto)):
        try:
            result = rung(video_id)
        except CouldNotRetrieveTranscript as exc:
            logger.info("transcript rung %s failed for %s: %s", rung_name, video_id, exc)
            continue
        if result is not None:
            return result

    try:
        return _fetch_ytdlp_subs(video_id, url)
    except DownloadError as exc:
        logger.info("transcript rung yt_dlp_subs failed for %s: %s", video_id, exc)
        return None


def _build_client() -> YouTubeTranscriptApi:
    """Wires §21.3's cookies/proxy plumbing into youtube-transcript-api.
    Both are `None`/unset by default, so local behaviour is unchanged.
    """
    proxy_config = None
    if settings.YTDLP_PROXY:
        proxy_config = GenericProxyConfig(
            http_url=settings.YTDLP_PROXY, https_url=settings.YTDLP_PROXY
        )
    http_client = requests.Session()
    if settings.YTDLP_COOKIES_FILE:
        cookie_jar = http.cookiejar.MozillaCookieJar(settings.YTDLP_COOKIES_FILE)
        cookie_jar.load(ignore_discard=True, ignore_expires=True)
        http_client.cookies = cookie_jar  # type: ignore[assignment]
    return YouTubeTranscriptApi(proxy_config=proxy_config, http_client=http_client)


def _fetch_manual(video_id: str) -> tuple[list[TranscriptCue], str] | None:
    return _fetch_by_kind(video_id, is_generated=False)


def _fetch_auto(video_id: str) -> tuple[list[TranscriptCue], str] | None:
    return _fetch_by_kind(video_id, is_generated=True)


def _fetch_by_kind(video_id: str, *, is_generated: bool) -> tuple[list[TranscriptCue], str] | None:
    transcript_list = _build_client().list(video_id)
    candidates = [t for t in transcript_list if t.is_generated == is_generated]
    transcript = _select_by_language(candidates)
    if transcript is None:
        return None
    fetched = transcript.fetch()
    cues = [
        TranscriptCue(start=snippet.start, end=snippet.start + snippet.duration, text=snippet.text)
        for snippet in fetched
    ]
    return cues, transcript.language_code


def _select_by_language(candidates: list[Any]) -> Any | None:
    """Prefer exact `en`, then any `en-*`, then the first available (§9.3)."""
    if not candidates:
        return None
    for candidate in candidates:
        if candidate.language_code == "en":
            return candidate
    for candidate in candidates:
        if candidate.language_code.startswith("en-"):
            return candidate
    return candidates[0]


def _fetch_ytdlp_subs(video_id: str, url: str) -> tuple[list[TranscriptCue], str] | None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        ydl_opts: dict[str, object] = {
            "writeautomaticsub": True,
            "writesubtitles": True,
            "subtitlesformat": "json3",
            "subtitleslangs": ["en.*"],
            "skip_download": True,
            "quiet": True,
            "no_warnings": True,
            "outtmpl": str(Path(tmp_dir) / "%(id)s.%(ext)s"),
        }
        if settings.YTDLP_COOKIES_FILE:
            ydl_opts["cookiefile"] = settings.YTDLP_COOKIES_FILE
        if settings.YTDLP_PROXY:
            ydl_opts["proxy"] = settings.YTDLP_PROXY

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        json3_files = sorted(Path(tmp_dir).glob(f"{video_id}*.json3"))
        if not json3_files:
            return None

        subtitle_path = json3_files[0]
        language = subtitle_path.stem.rsplit(".", 1)[-1]
        cues = _parse_json3(subtitle_path)
        if not cues:
            return None
        return cues, language


def _parse_json3(path: Path) -> list[TranscriptCue]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cues: list[TranscriptCue] = []
    for event in data.get("events", []):
        segs = event.get("segs")
        start_ms = event.get("tStartMs")
        duration_ms = event.get("dDurationMs")
        if segs is None or start_ms is None or duration_ms is None:
            continue
        text = "".join(seg.get("utf8", "") for seg in segs)
        if not text.strip():
            continue
        cues.append(
            TranscriptCue(start=start_ms / 1000, end=(start_ms + duration_ms) / 1000, text=text)
        )
    return cues
