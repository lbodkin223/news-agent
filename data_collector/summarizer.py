"""Generate structured briefings from scored articles.

Pulls unprocessed articles with relevance_score >= 3, categorizes them
by topic using keyword matching, and writes a structured markdown
briefing to disk.  No external API calls required.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from data_collector.config import SUMMARY_OUTPUT_DIR
from data_collector.database import (
    get_articles_for_summarization,
    get_connection,
    mark_articles_processed,
)

logger = logging.getLogger(__name__)

# ── category keywords (for sorting articles into sections) ───────────────────

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Datacenter Networking": [
        "datacenter networking", "data center networking",
        "network fabric", "spine-leaf", "leaf-spine",
        "top of rack", "peering", "internet exchange",
        "colocation", "buildout", "deployment",
        "outage", "topology",
    ],
    "Hardware & Interconnects": [
        "switch asic", "optical transceiver", "silicon photonics",
        "co-packaged optics", "optical interconnect",
        "coherent optics", "400g", "800g", "1.6t",
        "smartnic", "dpu",
        "broadcom", "arista", "cisco",
        "fiber optic", "wavelength",
    ],
    "AI Demand Signals": [
        "ai infrastructure", "ai cluster", "gpu cluster",
        "training cluster", "inference", "nvlink",
        "infiniband", "ultra ethernet",
        "accelerator", "gpu networking",
        "ai workload", "compute demand",
        "power cooling", "power delivery",
    ],
}

_LEADING_CHARS = 300

# ── helpers ──────────────────────────────────────────────────────────────────


def _lookback_iso(mode: str) -> str:
    """Return an ISO datetime string for the start of the lookback window."""
    now = datetime.now(tz=timezone.utc)
    if mode == "weekly":
        delta = timedelta(days=7)
    else:  # daily (default)
        delta = timedelta(hours=24)
    return (now - delta).isoformat()


def _categorize_article(article: dict) -> str:
    """Assign an article to a briefing section based on keyword matching."""
    searchable = (
        (article.get("title") or "") + " " +
        (article.get("extracted_text") or "")
    ).lower()

    best_category = "Worth Watching"
    best_count = 0

    for category, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in searchable)
        if count > best_count:
            best_count = count
            best_category = category

    return best_category


def _leading_text(article: dict) -> str:
    """Return the first ~300 characters of an article's body text."""
    body = (article.get("extracted_text") or "").strip()
    if not body:
        return ""
    truncated = body[:_LEADING_CHARS]
    # Try to break at a sentence boundary.
    last_period = truncated.rfind(".")
    if last_period > _LEADING_CHARS // 2:
        truncated = truncated[:last_period + 1]
    elif len(body) > _LEADING_CHARS:
        truncated += "..."
    return truncated


def _format_article_entry(article: dict) -> str:
    """Format a single article as a markdown list item."""
    score = article.get("relevance_score", "?")
    source = article.get("source", "unknown")
    if source.startswith("rss:"):
        source = "RSS"
    elif source.startswith("reddit:"):
        source = source.replace("reddit:", "")

    title = article.get("title", "Untitled")
    url = article.get("url", "")
    published = article.get("published_date", "")
    lead = _leading_text(article)

    lines = [f"- **[{title}]({url})** (score: {score}/5, via {source})"]
    if published:
        lines[0] += f"  \n  Published: {published}"
    if lead:
        lines.append(f"  > {lead}")

    return "\n".join(lines)


def _build_briefing_text(articles: list[dict], mode: str) -> str:
    """Build a structured markdown briefing from categorized articles."""
    categories: dict[str, list[dict]] = {
        "Datacenter Networking": [],
        "Hardware & Interconnects": [],
        "AI Demand Signals": [],
        "Worth Watching": [],
    }

    for article in articles:
        cat = _categorize_article(article)
        categories[cat].append(article)

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts: list[str] = [
        f"# News Agent — {mode.capitalize()} Briefing",
        f"*Generated {now} — {len(articles)} articles*\n",
    ]

    # Top stories: the 5 highest-scored articles across all categories.
    top = sorted(
        articles,
        key=lambda a: a.get("relevance_score", 0),
        reverse=True,
    )[:5]
    parts.append("## Top Stories")
    if top:
        for art in top:
            parts.append(_format_article_entry(art))
    else:
        parts.append("No notable developments this period.")
    parts.append("")

    for section_name in ("Datacenter Networking", "Hardware & Interconnects",
                         "AI Demand Signals", "Worth Watching"):
        parts.append(f"## {section_name}")
        section_articles = categories[section_name]
        if section_articles:
            section_articles.sort(
                key=lambda a: a.get("relevance_score", 0), reverse=True
            )
            for art in section_articles:
                parts.append(_format_article_entry(art))
        else:
            parts.append("No notable developments this period.")
        parts.append("")

    return "\n".join(parts)


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
) -> dict:
    """Produce a structured intelligence briefing.

    Args:
        mode: ``"daily"`` (last 24 h) or ``"weekly"`` (last 7 days).
        db_path: Optional override for the SQLite database path.
        output_dir: Where to write the briefing file.

    Returns a dict:
        articles_used  - number of articles included
        briefing_file  - absolute path to the written markdown file
        briefing_text  - the raw briefing markdown
    """
    out_dir = output_dir or SUMMARY_OUTPUT_DIR
    since = _lookback_iso(mode)

    with get_connection(db_path) as conn:
        articles = get_articles_for_summarization(conn, since=since)
        logger.info(
            "Found %d articles for %s briefing (since %s)",
            len(articles),
            mode,
            since,
        )

        if not articles:
            logger.info("No articles to include — skipping briefing generation.")
            return {
                "articles_used": 0,
                "briefing_file": None,
                "briefing_text": None,
            }

        briefing_text = _build_briefing_text(articles, mode)

        briefing_path = _write_briefing(briefing_text, mode, out_dir)
        logger.info("Briefing written to %s", briefing_path)

        consumed_ids = [a["id"] for a in articles]
        mark_articles_processed(conn, consumed_ids)
        conn.commit()
        logger.info("Marked %d articles as processed", len(consumed_ids))

    return {
        "articles_used": len(articles),
        "briefing_file": os.path.abspath(briefing_path),
        "briefing_text": briefing_text,
    }
