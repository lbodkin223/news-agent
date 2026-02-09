"""Collect stories from Hacker News that match configured keywords."""

import logging
from datetime import datetime, timezone
from typing import List, Optional

import requests

from data_collector.config import HN_API_BASE, HN_KEYWORDS, HN_MAX_STORIES
from data_collector.database import get_connection, insert_article

logger = logging.getLogger(__name__)

_SESSION = requests.Session()


def _get_json(url: str, timeout: int = 10):
    """GET a URL and return parsed JSON, or None on failure."""
    try:
        resp = _SESSION.get(url, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        logger.exception("HN API request failed: %s", url)
        return None


def _matches_keywords(text: str, keywords: List[str]) -> bool:
    """Return True if any keyword appears in text (case-insensitive)."""
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def _fetch_item(item_id: int) -> Optional[dict]:
    """Fetch a single HN item by ID."""
    return _get_json(f"{HN_API_BASE}/item/{item_id}.json")


def collect_hn(
    keywords: List[str] | None = None,
    max_stories: int | None = None,
    db_path: str | None = None,
) -> int:
    """Scan top and new HN stories for keyword matches.

    Returns the number of newly inserted articles.
    """
    kw = keywords or HN_KEYWORDS
    limit = max_stories or HN_MAX_STORIES
    inserted = 0

    # Gather story IDs from both top and new endpoints.
    story_ids: list[int] = []
    for endpoint in ("topstories", "newstories"):
        ids = _get_json(f"{HN_API_BASE}/{endpoint}.json")
        if ids:
            story_ids.extend(ids[:limit])

    # Deduplicate IDs while preserving order.
    seen_ids: set[int] = set()
    unique_ids: list[int] = []
    for sid in story_ids:
        if sid not in seen_ids:
            seen_ids.add(sid)
            unique_ids.append(sid)

    logger.info("Scanning %d HN stories for keywords: %s", len(unique_ids), kw)

    with get_connection(db_path) as conn:
        for item_id in unique_ids:
            item = _fetch_item(item_id)
            if not item or item.get("type") != "story":
                continue

            title = item.get("title", "")
            url = item.get("url") or f"https://news.ycombinator.com/item?id={item_id}"
            text = item.get("text", "") or ""
            searchable = f"{title} {text}"

            if not _matches_keywords(searchable, kw):
                continue

            published = None
            if item.get("time"):
                published = datetime.fromtimestamp(
                    item["time"], tz=timezone.utc
                ).isoformat()

            was_inserted = insert_article(
                conn,
                title=title,
                source="hackernews",
                url=url,
                published_date=published,
                raw_text=text or None,
            )
            if was_inserted:
                inserted += 1

        conn.commit()

    logger.info("HN collection complete — %d new articles", inserted)
    return inserted
