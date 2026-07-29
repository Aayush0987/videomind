"""Tests for app.core.prompts.load_prompt."""

from pathlib import Path

import pytest
from app.core import prompts


def test_load_prompt_reads_exact_file_content(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(prompts, "_PROMPTS_DIR", tmp_path)
    content = "You are a segmentation agent.\n\nReturn JSON only.\n"
    (tmp_path / "segmentation.md").write_text(content, encoding="utf-8")

    result = prompts.load_prompt("segmentation")

    assert result == content


def test_load_prompt_missing_file_raises_file_not_found_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(prompts, "_PROMPTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError):
        prompts.load_prompt("does_not_exist")
