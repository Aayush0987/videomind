"""Wikipedia REST summary client for entity enrichment (§10.6).

Free, keyless, citable. `fetch_summary` returns `None` on a 404 or a
disambiguation page so the caller can fall back to an LLM-generated blurb.
"""

import logging
import urllib.parse

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
_TIMEOUT = 10.0


class WikiSummary(BaseModel):
    title: str
    extract: str
    url: str


async def fetch_summary(
    title: str, *, client: httpx.AsyncClient | None = None
) -> WikiSummary | None:
    quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = _SUMMARY_URL.format(title=quoted)
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=_TIMEOUT)
    try:
        resp = await client.get(url, headers={"accept": "application/json"})
        if resp.status_code != 200:
            return None
        data = resp.json()
    except httpx.HTTPError:
        logger.warning("Wikipedia summary fetch failed for %r", title)
        return None
    finally:
        if owns_client:
            await client.aclose()

    if data.get("type") == "disambiguation":
        return None
    extract = (data.get("extract") or "").strip()
    if not extract:
        return None
    page_url = data.get("content_urls", {}).get("desktop", {}).get("page") or url
    return WikiSummary(title=data.get("title", title), extract=extract, url=page_url)
