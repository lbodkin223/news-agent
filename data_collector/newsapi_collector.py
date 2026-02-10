"""Collect articles from NewsAPI that match configured keywords."""

import logging
from datetime import datetime, timedelta, timezone
from typing import List

from newsapi import NewsApiClient
from newsapi.newsapi_exception import NewsAPIException

from data_collector.config import NEWSAPI_API_KEY, NEWSAPI_KEYWORDS
from data_collector.database import get_connection, insert_article

logger = logging.getLogger(__name__)


def collect_newsapi(
    keywords: List[str] | None = None,
    db_path: str | None = None,
) -> int:
    """Search NewsAPI /v2/everything for keyword matches.

    Returns the number of newly inserted articles.
    """
    if not NEWSAPI_API_KEY:
        logger.warning("NEWSAPI_API_KEY not configured — skipping NewsAPI collection.")
        return 0

    kw = keywords or NEWSAPI_KEYWORDS
    inserted = 0

    client = NewsApiClient(api_key=NEWSAPI_API_KEY)

    # Search the last 7 days (NewsAPI free tier keeps 30 days).
    from_date = (datetime.now(tz=timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")

    with get_connection(db_path) as conn:
        for keyword in kw:
            try:
                response = client.get_everything(
                    q=keyword,
                    from_param=from_date,
                    language="en",
                    sort_by="publishedAt",
                    page_size=50,
                )
            except NewsAPIException:
                logger.exception("NewsAPI request failed for keyword: %s", keyword)
                continue
            except Exception:
                logger.exception("Unexpected error fetching NewsAPI keyword: %s", keyword)
                continue

            articles = response.get("articles") or []
            logger.info(
                "NewsAPI keyword %r returned %d articles", keyword, len(articles)
            )

            for article in articles:
                url = article.get("url")
                if not url:
                    continue

                title = article.get("title") or "Untitled"
                description = article.get("description") or ""
                content = article.get("content") or ""
                raw_text = f"{description}\n\n{content}".strip() or None

                published = article.get("publishedAt")  # already ISO format

                was_inserted = insert_article(
                    conn,
                    title=title,
                    source="newsapi",
                    url=url,
                    published_date=published,
                    raw_text=raw_text,
                )
                if was_inserted:
                    inserted += 1

        conn.commit()

    logger.info("NewsAPI collection complete — %d new articles", inserted)
    return inserted
