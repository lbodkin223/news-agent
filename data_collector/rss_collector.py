"""Collect articles from RSS feeds using feedparser."""

import logging
from typing import List

import feedparser

from data_collector.config import RSS_FEEDS
from data_collector.database import get_connection, insert_article

logger = logging.getLogger(__name__)


def _parse_published(entry) -> str | None:
    """Extract a published date string from a feed entry."""
    for attr in ("published", "updated", "created"):
        value = getattr(entry, attr, None)
        if value:
            return value
    return None


def _entry_text(entry) -> str | None:
    """Extract the best available body text from a feed entry."""
    if hasattr(entry, "content") and entry.content:
        return entry.content[0].get("value", "")
    return getattr(entry, "summary", None)


def collect_rss(feed_urls: List[str] | None = None, db_path: str | None = None) -> int:
    """Parse each RSS feed and insert new articles.

    Returns the number of newly inserted articles.
    """
    urls = feed_urls or RSS_FEEDS
    inserted = 0

    with get_connection(db_path) as conn:
        for feed_url in urls:
            logger.info("Fetching RSS feed: %s", feed_url)
            try:
                feed = feedparser.parse(feed_url)
            except Exception:
                logger.exception("Failed to parse feed: %s", feed_url)
                continue

            if feed.bozo and not feed.entries:
                logger.warning("Feed returned no entries: %s", feed_url)
                continue

            for entry in feed.entries:
                link = getattr(entry, "link", None)
                title = getattr(entry, "title", "Untitled")
                if not link:
                    continue

                was_inserted = insert_article(
                    conn,
                    title=title,
                    source=f"rss:{feed_url}",
                    url=link,
                    published_date=_parse_published(entry),
                    raw_text=_entry_text(entry),
                )
                if was_inserted:
                    inserted += 1

        conn.commit()

    logger.info("RSS collection complete — %d new articles", inserted)
    return inserted
