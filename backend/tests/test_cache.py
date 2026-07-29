"""Cache semantics for `POST /api/videos` (§12.3, Phase 8 DoD).

The headline guarantee (criterion A8): a second analyze request for an
already-indexed video is a cache *hit* that returns immediately and makes zero
LLM calls, while `force_refresh` forces a fresh run. The analysis itself is
stubbed at the scheduler boundary — the first request "completes" by writing a
ready video row, exactly as a finished job would.
"""

from collections.abc import Iterator

import pytest
from app import config
from app.api import routes_videos
from app.core import db, embedder
from fastapi.testclient import TestClient

from test_api import FakeEmbedder

_URL = "https://youtu.be/dQw4w9WgXcQ"
_VIDEO_ID = "dQw4w9WgXcQ"


def _write_ready_video() -> None:
    conn = db.get_connection()
    db.init_schema(conn)
    db.upsert_video(
        conn,
        video_id=_VIDEO_ID,
        url=_URL,
        title="A Title",
        channel=None,
        duration=100.0,
        thumbnail_url=None,
        published_at=None,
        transcript_source="captions",
        language="en",
    )


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, list]]:
    monkeypatch.setattr(config.settings, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(embedder, "_embedder", FakeEmbedder())

    schedule_calls: list[str] = []

    def fake_schedule(job_id: str, url: str, llm: object) -> None:
        # Stand in for a completed analysis job: the video is now cached.
        schedule_calls.append(job_id)
        _write_ready_video()

    monkeypatch.setattr(routes_videos.jobs, "schedule", fake_schedule)
    import app.main

    with TestClient(app.main.app) as test_client:
        yield test_client, schedule_calls


def test_second_analyze_is_a_cache_hit_with_no_new_work(client) -> None:
    test_client, schedule_calls = client

    # 1. First request misses, schedules the (stubbed) analysis → 202.
    first = test_client.post("/api/videos", json={"url": _URL})
    assert first.status_code == 202
    assert first.json()["cached"] is False
    assert len(schedule_calls) == 1

    # 2. Second request for the same url is a hit → 200, no new scheduling.
    second = test_client.post("/api/videos", json={"url": _URL})
    assert second.status_code == 200
    assert second.json() == {"cached": True, "video_id": _VIDEO_ID, "job_id": None}
    assert len(schedule_calls) == 1  # the cache hit did no background work


def test_force_refresh_reruns_even_when_cached(client) -> None:
    test_client, schedule_calls = client
    _write_ready_video()  # pretend a prior run already cached it

    hit = test_client.post("/api/videos", json={"url": _URL})
    assert hit.json()["cached"] is True
    assert schedule_calls == []

    refreshed = test_client.post("/api/videos", json={"url": _URL, "force_refresh": True})
    assert refreshed.status_code == 202
    assert refreshed.json()["cached"] is False
    assert len(schedule_calls) == 1


def test_stale_analysis_version_is_a_miss(client, monkeypatch) -> None:
    test_client, schedule_calls = client
    _write_ready_video()
    # A prompt/segmentation change bumps the version; the old row no longer hits.
    monkeypatch.setattr(config, "CURRENT_ANALYSIS_VERSION", config.CURRENT_ANALYSIS_VERSION + 1)
    monkeypatch.setattr(routes_videos, "CURRENT_ANALYSIS_VERSION", config.CURRENT_ANALYSIS_VERSION)

    resp = test_client.post("/api/videos", json={"url": _URL})
    assert resp.status_code == 202
    assert resp.json()["cached"] is False
