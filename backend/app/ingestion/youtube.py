"""URL parsing (`parse_video_id`) and metadata fetch via YouTube Data API v3,
yt-dlp fallback (§9.1, §9.2).
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qs, urlparse

import httpx
import yt_dlp
from yt_dlp.utils import DownloadError

from app.config import settings
from app.core.errors import MetadataUnavailableError, UnsupportedSourceError

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_DURATION_RE = re.compile(r"^PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$")


@dataclass
class VideoMetadata:
    video_id: str
    title: str
    channel: str | None
    duration: float
    thumbnail_url: str | None
    published_at: str | None
    source: Literal["youtube_api", "yt_dlp"]


def parse_video_id(url: str) -> str:
    candidate = url.strip()
    if _VIDEO_ID_RE.match(candidate):
        return candidate

    normalized = candidate if "://" in candidate else f"https://{candidate}"
    parsed = urlparse(normalized)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    segments = [s for s in parsed.path.split("/") if s]

    video_id = None
    if host in ("youtube.com", "youtube-nocookie.com"):
        if segments and segments[0] == "watch":
            video_id = parse_qs(parsed.query).get("v", [None])[0]
        elif len(segments) >= 2 and segments[0] in ("shorts", "embed"):
            video_id = segments[1]
    elif host == "youtu.be" and segments:
        video_id = segments[0]

    if video_id and _VIDEO_ID_RE.match(video_id):
        return video_id
    raise UnsupportedSourceError(f"Could not parse a YouTube video id from {url!r}.")


def fetch_metadata(video_id: str) -> VideoMetadata:
    if settings.YOUTUBE_API_KEY:
        return _fetch_metadata_youtube_api(video_id)
    return _fetch_metadata_yt_dlp(video_id)


def _fetch_metadata_youtube_api(video_id: str) -> VideoMetadata:
    try:
        response = httpx.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,contentDetails",
                "id": video_id,
                "key": settings.YOUTUBE_API_KEY,
            },
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MetadataUnavailableError(
            f"YouTube Data API request failed for {video_id!r}."
        ) from exc

    items = response.json().get("items", [])
    if not items:
        raise MetadataUnavailableError(f"No metadata found for video {video_id!r}.")

    snippet = items[0]["snippet"]
    duration = _parse_iso8601_duration(items[0]["contentDetails"]["duration"])
    return VideoMetadata(
        video_id=video_id,
        title=snippet["title"],
        channel=snippet.get("channelTitle"),
        duration=duration,
        thumbnail_url=snippet.get("thumbnails", {}).get("medium", {}).get("url"),
        published_at=snippet.get("publishedAt"),
        source="youtube_api",
    )


def _fetch_metadata_yt_dlp(video_id: str) -> VideoMetadata:
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts: dict[str, object] = {"skip_download": True, "quiet": True, "no_warnings": True}
    if settings.YTDLP_COOKIES_FILE:
        ydl_opts["cookiefile"] = settings.YTDLP_COOKIES_FILE
    if settings.YTDLP_PROXY:
        ydl_opts["proxy"] = settings.YTDLP_PROXY

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as exc:
        raise MetadataUnavailableError(
            f"yt-dlp metadata extraction failed for {video_id!r}."
        ) from exc

    return VideoMetadata(
        video_id=video_id,
        title=info["title"],
        channel=info.get("uploader"),
        duration=float(info["duration"]),
        thumbnail_url=info.get("thumbnail"),
        published_at=_yt_dlp_upload_date_to_iso(info.get("upload_date")),
        source="yt_dlp",
    )


def _yt_dlp_upload_date_to_iso(upload_date: str | None) -> str | None:
    if not upload_date:
        return None
    return datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=UTC).date().isoformat()


def _parse_iso8601_duration(value: str) -> float:
    match = _DURATION_RE.match(value)
    if not match:
        raise MetadataUnavailableError(f"Unparseable ISO-8601 duration: {value!r}.")
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return float(hours * 3600 + minutes * 60 + seconds)
