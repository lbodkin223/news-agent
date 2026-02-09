"""Generate structured intelligence briefings from scored articles.

Pulls unprocessed articles with relevance_score >= 3, groups them into
a prompt, sends the batch to the Anthropic API (claude-sonnet-4-5 for cost
efficiency), and writes the resulting briefing to disk.  Marks every
article included in the briefing as processed afterward.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import anthropic

from data_collector.config import (
    ANTHROPIC_MODEL,
    SUMMARY_MAX_ARTICLE_CHARS,
    SUMMARY_MAX_TOTAL_CHARS,
    SUMMARY_OUTPUT_DIR,
)
from data_collector.database import (
    get_articles_for_summarization,
    get_connection,
    mark_articles_processed,
)

logger = logging.getLogger(__name__)

# ── system prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an expert analyst producing a concise intelligence briefing on
datacenter networking, hardware interconnects, and AI infrastructure.

You will receive a batch of news articles (title, source, URL, and body
text).  Synthesise them into the structured briefing format below.
Combine related articles where appropriate rather than repeating each
one individually.  Include source links inline using markdown:
[Source Name](url).

If a section has no relevant articles, write "No notable developments
this period." rather than omitting the section.

Output format (use these exact markdown headings):

## Top Stories
3-5 most important developments across all categories.  Each item gets
2-3 sentences summarising the news and its significance.

## Datacenter Networking
Infrastructure buildouts, topology changes, new deployments,
spine-leaf or fabric architecture news, major outages, peering/IX
developments.

## Hardware & Interconnects
Switch ASICs (Memory / Memory / memory), optical transceivers (400G/800G/1.6T),
silicon photonics, co-packaged optics, cable & connector developments,
NIC and DPU news.

## AI Demand Signals
Training cluster announcements, inference scaling, GPU/accelerator
networking (NVLink, UEC, Ultra Ethernet), power and cooling
constraints driven by AI workloads.

## Worth Watching
Emerging trends, early-stage research, interesting discussion threads,
rumors, or anything that doesn't fit the categories above but is worth
tracking.
"""

# ── helpers ──────────────────────────────────────────────────────────────────


def _lookback_iso(mode: str) -> str:
    """Return an ISO datetime string for the start of the lookback window."""
    now = datetime.now(tz=timezone.utc)
    if mode == "weekly":
        delta = timedelta(days=7)
    else:  # daily (default)
        delta = timedelta(hours=24)
    return (now - delta).isoformat()


def _build_articles_block(articles: list[dict]) -> str:
    """Format articles into a numbered text block for the user message."""
    parts: list[str] = []
    total_chars = 0
    for i, art in enumerate(articles, 1):
        body = (art["extracted_text"] or art.get("raw_text") or "").strip()
        body = body[:SUMMARY_MAX_ARTICLE_CHARS]

        entry = (
            f"### Article {i}\n"
            f"**Title:** {art['title']}\n"
            f"**Source:** {art['source']}\n"
            f"**URL:** {art['url']}\n"
            f"**Published:** {art.get('published_date', 'unknown')}\n"
            f"**Relevance score:** {art['relevance_score']}/5\n\n"
            f"{body}\n"
        )

        if total_chars + len(entry) > SUMMARY_MAX_TOTAL_CHARS:
            logger.warning(
                "Truncating article batch at %d / %d articles (prompt size limit)",
                i - 1,
                len(articles),
            )
            break

        parts.append(entry)
        total_chars += len(entry)

    return "\n---\n".join(parts)


def _write_briefing(text: str, mode: str, output_dir: str) -> str:
    """Write the briefing markdown to disk and return the file path."""
    os.makedirs(output_dir, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    filename = f"briefing_{mode}_{ts}.md"
    path = os.path.join(output_dir, filename)
    with open(path, "w") as fh:
        fh.write(text)
    return path


# ── public API ───────────────────────────────────────────────────────────────


def generate_briefing(
    mode: str = "daily",
    db_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    client: anthropic.Anthropic | None = None,
) -> dict:
    """Produce a structured intelligence briefing.

    Args:
        mode: ``"daily"`` (last 24 h) or ``"weekly"`` (last 7 days).
        db_path: Optional override for the SQLite database path.
        output_dir: Where to write the briefing file.
        client: Optional pre-built Anthropic client (for testing).

    Returns a dict:
        articles_used  – number of articles included in the prompt
        briefing_file  – absolute path to the written markdown file
        briefing_text  – the raw briefing markdown
    """
    out_dir = output_dir or SUMMARY_OUTPUT_DIR
    since = _lookback_iso(mode)
    api_client = client or anthropic.Anthropic()

    with get_connection(db_path) as conn:
        articles = get_articles_for_summarization(conn, since=since)
        logger.info(
            "Found %d articles for %s briefing (since %s)",
            len(articles),
            mode,
            since,
        )

        if not articles:
            logger.info("No articles to summarise — skipping briefing generation.")
            return {
                "articles_used": 0,
                "briefing_file": None,
                "briefing_text": None,
            }

        # Build the user message with all article content.
        articles_block = _build_articles_block(articles)
        user_message = (
            f"Generate a **{mode}** intelligence briefing from the following "
            f"{len(articles)} articles.\n\n{articles_block}"
        )

        logger.info(
            "Sending %d articles (%d chars) to Anthropic for summarisation",
            len(articles),
            len(user_message),
        )

        message = api_client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        briefing_text = message.content[0].text

        # Write to disk.
        briefing_path = _write_briefing(briefing_text, mode, out_dir)
        logger.info("Briefing written to %s", briefing_path)

        # Mark every article we consumed as processed.
        consumed_ids = [a["id"] for a in articles]
        mark_articles_processed(conn, consumed_ids)
        conn.commit()
        logger.info("Marked %d articles as processed", len(consumed_ids))

    return {
        "articles_used": len(articles),
        "briefing_file": os.path.abspath(briefing_path),
        "briefing_text": briefing_text,
    }
