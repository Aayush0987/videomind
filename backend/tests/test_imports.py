"""Smoke test: app.config imports and Settings() loads with no env vars set."""

from app.config import Settings


def test_settings_loads() -> None:
    settings = Settings(_env_file=None)
    assert settings.EMBEDDING_DIM == 768
