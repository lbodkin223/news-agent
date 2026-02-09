"""Main entry point — orchestrates data collection, extraction, and scoring."""

import argparse
import logging
import sys

from data_collector.database import count_articles, init_db
from data_collector.hn_collector import collect_hn
from data_collector.pipeline import process_articles
from data_collector.reddit_collector import collect_reddit
from data_collector.rss_collector import collect_rss
from data_collector.summarizer import generate_briefing

logger = logging.getLogger(__name__)


def run_all(db_path: str | None = None) -> dict[str, int]:
    """Run every collector and return per-source insert counts."""
    init_db(db_path)

    results: dict[str, int] = {}

    logger.info("=== Starting RSS collection ===")
    results["rss"] = collect_rss(db_path=db_path)

    logger.info("=== Starting Reddit collection ===")
    results["reddit"] = collect_reddit(db_path=db_path)

    logger.info("=== Starting Hacker News collection ===")
    results["hackernews"] = collect_hn(db_path=db_path)

    total_new = sum(results.values())
    total_db = count_articles(db_path)
    logger.info(
        "Collection finished — %d new articles (%d total in database)",
        total_new,
        total_db,
    )
    return results


def main():
    parser = argparse.ArgumentParser(description="Collect news articles from multiple sources")
    parser.add_argument(
        "--sources",
        nargs="+",
        choices=["rss", "reddit", "hackernews", "all"],
        default=["all"],
        help="Which sources to collect from (default: all)",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database (overrides NEWS_AGENT_DB env var)",
    )
    parser.add_argument(
        "--process",
        action="store_true",
        help="Run extraction and relevance scoring after collection",
    )
    parser.add_argument(
        "--process-only",
        action="store_true",
        help="Only run extraction and scoring (skip collection)",
    )
    parser.add_argument(
        "--summarize",
        action="store_true",
        help="Generate an intelligence briefing after processing",
    )
    parser.add_argument(
        "--summarize-only",
        action="store_true",
        help="Only generate a briefing (skip collection and processing)",
    )
    parser.add_argument(
        "--mode",
        choices=["daily", "weekly"],
        default="daily",
        help="Briefing lookback window: last 24h or 7 days (default: daily)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for briefing files (overrides NEWS_AGENT_SUMMARY_DIR)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    init_db(args.db)

    skip_collect = args.process_only or args.summarize_only
    skip_process = args.summarize_only
    run_summarize = args.summarize or args.summarize_only

    if not skip_collect:
        sources = set(args.sources)
        if "all" in sources:
            results = run_all(db_path=args.db)
        else:
            results = {}
            if "rss" in sources:
                results["rss"] = collect_rss(db_path=args.db)
            if "reddit" in sources:
                results["reddit"] = collect_reddit(db_path=args.db)
            if "hackernews" in sources:
                results["hackernews"] = collect_hn(db_path=args.db)

        total = sum(results.values())
        print(f"Collection done. Inserted {total} new articles: {results}")

    if not skip_process and (args.process or args.process_only):
        logger.info("=== Starting extraction & scoring pipeline ===")
        stats = process_articles(db_path=args.db)
        print(
            f"Processing done. extracted={stats['extracted']}, "
            f"scored={stats['scored']}, flagged={stats['flagged']}, "
            f"skipped={stats['skipped']}"
        )

    if run_summarize:
        logger.info("=== Generating %s briefing ===", args.mode)
        result = generate_briefing(
            mode=args.mode,
            db_path=args.db,
            output_dir=args.output_dir,
        )
        if result["briefing_file"]:
            print(
                f"Briefing generated from {result['articles_used']} articles: "
                f"{result['briefing_file']}"
            )
        else:
            print("No articles available for briefing.")


if __name__ == "__main__":
    main()
