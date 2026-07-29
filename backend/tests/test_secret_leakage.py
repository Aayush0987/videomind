"""Secret-leakage guard (§7.3, §17, Phase 8 DoD).

Run a full (faked) analysis with a sentinel API key threaded through the
`LLMConfig`, then prove the key is absent from every durable surface: the
SQLite file, the MLflow run directory, and the captured logs. The key must live
only in memory for the duration of the request (§16.7's promise made true).
"""

import logging
from pathlib import Path

import pytest
from app.config import settings
from app.core.llm import LLMConfig
from app.graphs import analysis_graph as g

from test_analysis_graph import _fake, _wire

_SENTINEL = "SENTINEL_KEY_9Z"
_URL = "https://youtu.be/abcdefghijk"


def _all_file_bytes(root: Path) -> bytes:
    blob = b""
    for path in root.rglob("*"):
        if path.is_file():
            blob += path.read_bytes()
    return blob


@pytest.mark.asyncio
async def test_api_key_never_reaches_disk_mlflow_or_logs(
    monkeypatch: pytest.MonkeyPatch, tmp_path, caplog
) -> None:
    monkeypatch.setattr(settings, "MLFLOW_TRACKING_URI", f"file:{tmp_path}/mlruns")
    fake = _fake([200.0, 400.0])
    _wire(monkeypatch, fake, tmp_path, mlflow_enabled=True)

    with caplog.at_level(logging.DEBUG):
        result = await g.run_analysis(
            "secret-job", _URL, LLMConfig(api_key=_SENTINEL, provider="gemini")
        )

    assert result["verification"].valid  # the run actually completed

    # 1. SQLite: the video/transcript/chapter rows must not contain the key.
    sqlite_path = tmp_path / "videomind.sqlite3"
    assert sqlite_path.exists()
    assert _SENTINEL.encode() not in sqlite_path.read_bytes()

    # 2. MLflow: params/metrics/artifacts logged for the run must be key-free.
    mlruns = tmp_path / "mlruns"
    assert mlruns.exists()
    assert _SENTINEL.encode() not in _all_file_bytes(mlruns)

    # 3. Logs: nothing wrote the key to a log line.
    assert _SENTINEL not in caplog.text


def test_llmconfig_repr_hides_the_key() -> None:
    cfg = LLMConfig(api_key=_SENTINEL)
    assert _SENTINEL not in repr(cfg)
    assert "key=set" in repr(cfg)
