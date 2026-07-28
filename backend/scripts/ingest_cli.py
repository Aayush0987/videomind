"""CLI entry point: process one YouTube URL through ingestion without the API (§22 Phase 2)."""

import argparse
import sys

from app.core import db
from app.core.errors import VideoMindError
from app.ingestion import normalize, youtube
from app.schemas.transcript import TranscriptCue
from app.services import pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--stop-after", choices=["metadata", "transcript"], default="transcript")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    try:
        video_id = youtube.parse_video_id(args.url)
        conn = db.get_connection()
        db.init_schema(conn)

        existing = db.get_video(conn, video_id)
        if existing is not None and not args.force_refresh:
            cues = db.get_transcript_cues(conn, video_id)
            units = normalize.normalize(cues) if cues else []
            print(
                f"video_id={video_id} title={existing.title!r} "
                f"duration={existing.duration} transcript_source={existing.transcript_source} "
                f"language={existing.language} unit_count={len(units)} cached=true"
            )
            return 0

        metadata = youtube.fetch_metadata(video_id)
        if args.stop_after == "metadata":
            print(
                f"video_id={metadata.video_id} title={metadata.title!r} "
                f"channel={metadata.channel!r} duration={metadata.duration} "
                f"source={metadata.source}"
            )
            return 0

        transcript = pipeline.acquire_transcript(video_id, args.url, metadata.duration)

        db.upsert_video(
            conn,
            video_id=video_id,
            url=args.url,
            title=metadata.title,
            channel=metadata.channel,
            duration=metadata.duration,
            thumbnail_url=metadata.thumbnail_url,
            published_at=metadata.published_at,
            transcript_source=transcript.source,
            language=transcript.language,
        )
        cues_to_store = [
            TranscriptCue(start=unit.start, end=unit.end, text=unit.text)
            for unit in transcript.units
        ]
        db.upsert_transcript(conn, video_id, cues_to_store)

        print(
            f"video_id={video_id} title={metadata.title!r} duration={metadata.duration} "
            f"transcript_source={transcript.source} language={transcript.language} "
            f"unit_count={len(transcript.units)} cached=false"
        )
        return 0
    except VideoMindError as exc:
        print(f"{exc.error_code}: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
