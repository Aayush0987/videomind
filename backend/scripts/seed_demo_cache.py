"""Pre-bakes demo videos locally into `backend/data/seed/` for a resilient
deployed demo (§21.3).

Runs the full analysis graph on a handful of hand-picked videos *locally* —
where YouTube fetching works — and writes the resulting SQLite rows and Chroma
collection into ``backend/data/seed/``. Because local and production share one
embedding backend (``gemini-embedding-001`` at 768d), a single run produces
artefacts that are valid in both places. The Docker image copies this directory
into ``DATA_DIR`` on first boot when the database is empty, so the deployed demo
always has working videos regardless of network conditions.

Usage::

    # from repo root, with a Gemini key in .env
    python backend/scripts/seed_demo_cache.py <url> [<url> ...]
    python backend/scripts/seed_demo_cache.py            # uses DEMO_URLS below

The curated demo set is intentionally left for the maintainer to fill in with
three real links (10–30 min technical talks with captions). Passing URLs on the
command line overrides the list.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

# Curated demo videos. Fill in three real YouTube links (10–30 min technical
# talks with captions) before shipping, or pass URLs on the command line.
DEMO_URLS: list[str] = []


async def _seed_one(url: str) -> str:
    # Imported lazily so DATA_DIR is already patched before db/vectorstore init.
    from app.api.deps import resolve_llm_config
    from app.core import db
    from app.core.errors import VideoMindError
    from app.graphs.analysis_graph import run_analysis
    from app.ingestion import youtube
    from app.services import jobs

    video_id = youtube.parse_video_id(url)
    job_id = uuid.uuid4().hex
    jobs.create(job_id, url)
    llm = resolve_llm_config(None)

    try:
        result = await run_analysis(job_id, url, llm)
    except VideoMindError as exc:
        return f"  x {url} -- {exc.error_code}: {exc.message}"

    conn = db.get_connection()
    chapters = db.get_chapters(conn, result["video_id"])
    return f"  ok {result['video_id']} ({video_id}) -- {len(chapters)} chapters"


async def _run(urls: list[str], out_dir: Path) -> int:
    # Point every store (SQLite, Chroma) at the seed directory, and keep the run
    # out of MLflow so the seed dir stays clean.
    from app.config import settings

    settings.DATA_DIR = str(out_dir)
    settings.MLFLOW_ENABLED = False

    from app.core import db

    db.reset_connection()
    db.init_schema(db.get_connection())

    print(f"Seeding {len(urls)} video(s) into {out_dir}/")
    lines = [await _seed_one(url) for url in urls]
    print("\n".join(lines))

    failures = sum(1 for line in lines if line.strip().startswith("x "))
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="YouTube URLs to seed")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "data" / "seed"),
        help="Output directory for the seed cache (default: backend/data/seed)",
    )
    args = parser.parse_args()

    urls = args.urls or DEMO_URLS
    if not urls:
        print(
            "No URLs given and DEMO_URLS is empty. Pass one or more YouTube "
            "links, or fill in the curated DEMO_URLS list.",
            file=sys.stderr,
        )
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    return asyncio.run(_run(urls, out_dir))


if __name__ == "__main__":
    sys.exit(main())
