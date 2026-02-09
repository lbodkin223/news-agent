"""Processing pipeline: extract text → score relevance → update DB."""

import logging
from typing import Optional

from data_collector.database import (
    get_connection,
    get_unprocessed_articles,
    mark_processed,
    update_extracted_text,
    update_relevance_score,
)
from data_collector.extractor import extract_text
from data_collector.scorer import score_article

logger = logging.getLogger(__name__)


def process_articles(db_path: Optional[str] = None) -> dict[str, int]:
    """Run extraction and scoring on all unprocessed articles.

    Returns a dict with counts:
      extracted  – articles where body text was successfully pulled
      scored     – articles that received a relevance score
      flagged    – articles scoring >= 3 (flagged for summarization)
      skipped    – articles where extraction failed and had no fallback text
    """
    stats = {"extracted": 0, "scored": 0, "flagged": 0, "skipped": 0}

    with get_connection(db_path) as conn:
        rows = get_unprocessed_articles(conn)
        logger.info("Processing %d unprocessed articles", len(rows))

        for article_id, title, url, raw_text in rows:
            # --- Step 1: extract full article text ---
            text = extract_text(url, existing_raw=raw_text)

            if not text:
                logger.info("Skipping (no text): [%d] %s", article_id, title)
                mark_processed(conn, article_id)
                stats["skipped"] += 1
                continue

            update_extracted_text(conn, article_id, text)
            stats["extracted"] += 1

            # --- Step 2: score relevance ---
            score = score_article(title, text)
            update_relevance_score(conn, article_id, score, mark_processed=True)
            stats["scored"] += 1

            if score >= 3:
                stats["flagged"] += 1
                logger.info(
                    "Flagged (score=%d): [%d] %s", score, article_id, title
                )
            else:
                logger.debug(
                    "Low relevance (score=%d): [%d] %s", score, article_id, title
                )

        conn.commit()

    logger.info(
        "Processing complete — extracted=%d, scored=%d, flagged=%d, skipped=%d",
        stats["extracted"],
        stats["scored"],
        stats["flagged"],
        stats["skipped"],
    )
    return stats
