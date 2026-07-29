"""Tests for core/wikipedia.fetch_summary (§10.6)."""

import httpx
import pytest
from app.core.wikipedia import fetch_summary


class _FakeClient:
    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self.requested_url: str | None = None

    async def get(self, url: str, headers: dict | None = None) -> httpx.Response:
        self.requested_url = url
        return self._response


@pytest.mark.asyncio
async def test_returns_summary_on_200() -> None:
    resp = httpx.Response(
        200,
        json={
            "type": "standard",
            "title": "Ada Lovelace",
            "extract": "Ada Lovelace was an English mathematician.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Ada_Lovelace"}},
        },
    )
    client = _FakeClient(resp)

    result = await fetch_summary("Ada Lovelace", client=client)

    assert result is not None
    assert result.extract.startswith("Ada Lovelace was")
    assert result.url == "https://en.wikipedia.org/wiki/Ada_Lovelace"
    # Spaces are underscored and percent-encoded in the request path.
    assert "Ada_Lovelace" in (client.requested_url or "")


@pytest.mark.asyncio
async def test_returns_none_on_404() -> None:
    result = await fetch_summary("Nonexistent", client=_FakeClient(httpx.Response(404)))
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_on_disambiguation() -> None:
    resp = httpx.Response(200, json={"type": "disambiguation", "extract": "May refer to:"})
    result = await fetch_summary("Mercury", client=_FakeClient(resp))
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_on_empty_extract() -> None:
    resp = httpx.Response(200, json={"type": "standard", "extract": "   "})
    result = await fetch_summary("Blank", client=_FakeClient(resp))
    assert result is None
