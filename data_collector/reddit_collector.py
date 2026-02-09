"""Collect top posts from subreddits using PRAW."""

import logging
from typing import List, Optional

import praw

from data_collector.config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_POST_LIMIT,
    REDDIT_USER_AGENT,
    SUBREDDITS,
)
from data_collector.database import get_connection, insert_article

logger = logging.getLogger(__name__)


def _make_reddit_client(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> praw.Reddit:
    """Create a read-only PRAW Reddit instance."""
    return praw.Reddit(
        client_id=client_id or REDDIT_CLIENT_ID,
        client_secret=client_secret or REDDIT_CLIENT_SECRET,
        user_agent=user_agent or REDDIT_USER_AGENT,
    )


def _post_published(submission) -> str:
    """Return an ISO-formatted string from a submission's created_utc."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat()


def collect_reddit(
    subreddits: List[str] | None = None,
    limit: int | None = None,
    db_path: str | None = None,
    reddit_client: praw.Reddit | None = None,
) -> int:
    """Fetch hot posts from each subreddit and store them.

    Returns the number of newly inserted articles.
    """
    subs = subreddits or SUBREDDITS
    post_limit = limit or REDDIT_POST_LIMIT
    inserted = 0

    if not (REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET) and reddit_client is None:
        logger.warning(
            "Reddit credentials not configured — set REDDIT_CLIENT_ID and "
            "REDDIT_CLIENT_SECRET environment variables. Skipping Reddit collection."
        )
        return 0

    reddit = reddit_client or _make_reddit_client()

    with get_connection(db_path) as conn:
        for sub_name in subs:
            logger.info("Fetching subreddit: r/%s", sub_name)
            try:
                subreddit = reddit.subreddit(sub_name)
                for submission in subreddit.hot(limit=post_limit):
                    url = f"https://www.reddit.com{submission.permalink}"
                    raw_text = submission.selftext or None

                    was_inserted = insert_article(
                        conn,
                        title=submission.title,
                        source=f"reddit:r/{sub_name}",
                        url=url,
                        published_date=_post_published(submission),
                        raw_text=raw_text,
                    )
                    if was_inserted:
                        inserted += 1
            except Exception:
                logger.exception("Error fetching r/%s", sub_name)
                continue

        conn.commit()

    logger.info("Reddit collection complete — %d new articles", inserted)
    return inserted
