#!/usr/bin/env python3
"""news-agent — full pipeline entry point.

Runs:  collect → extract → score → summarise → deliver

Designed to be called from cron:

    # Daily at 07:00 UTC
    0 7 * * * cd /opt/news-agent && /usr/bin/python3 main.py --daily

    # Weekly on Monday at 08:00 UTC
    0 8 * * 1 cd /opt/news-agent && /usr/bin/python3 main.py --weekly
"""

import argparse
import logging
import sys
from datetime import datetime, timezone

from data_collector.collector import run_all
from data_collector.database import init_db
from data_collector.delivery import deliver
from data_collector.pipeline import process_articles
from data_collector.summarizer import generate_briefing

logger = logging.getLogger("news_agent")


def run_pipeline(
    mode: str = "daily",
    db_path: str | None = None,
    output_dir: str | None = None,
    email_to: str | None = None,
    skip_collect: bool = False,
    skip_email: bool = False,
) -> dict:
    """Execute the full pipeline and return a result summary."""
    results: dict = {
        "mode": mode,
        "collected": {},
        "processed": {},
        "briefing_articles": 0,
        "delivery": {},
    }

    init_db(db_path)

    # ── 1. Collect ───────────────────────────────────────────────────────
    if not skip_collect:
        logger.info("=== Step 1/4: Collecting articles ===")
        results["collected"] = run_all(db_path=db_path)
    else:
        logger.info("=== Step 1/4: Collection skipped ===")

    # ── 2. Extract + Score ───────────────────────────────────────────────
    logger.info("=== Step 2/4: Extracting text & scoring relevance ===")
    results["processed"] = process_articles(db_path=db_path)

    # ── 3. Summarise ─────────────────────────────────────────────────────
    logger.info("=== Step 3/4: Generating %s briefing ===", mode)
    briefing = generate_briefing(mode=mode, db_path=db_path, output_dir=output_dir)
    results["briefing_articles"] = briefing["articles_used"]

    # ── 4. Deliver ───────────────────────────────────────────────────────
    if briefing["briefing_text"]:
        logger.info("=== Step 4/4: Delivering briefing ===")
        results["delivery"] = deliver(
            briefing["briefing_text"],
            mode=mode,
            output_dir=output_dir,
            email_to=email_to,
            skip_email=skip_email,
        )
    else:
        logger.info("=== Step 4/4: No briefing to deliver ===")
        results["delivery"] = {"file": None, "email": False}

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="news-agent",
        description="Full news intelligence pipeline: collect → extract → score → summarise → deliver",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--daily",
        action="store_const",
        const="daily",
        dest="mode",
        help="Run in daily mode (last 24 hours)",
    )
    mode_group.add_argument(
        "--weekly",
        action="store_const",
        const="weekly",
        dest="mode",
        help="Run in weekly mode (last 7 days)",
    )

    parser.add_argument(
        "--db",
        default=None,
        help="Path to SQLite database (overrides NEWS_AGENT_DB env var)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for briefing files (overrides NEWS_AGENT_OUTPUT_DIR)",
    )
    parser.add_argument(
        "--email-to",
        default=None,
        help="Override EMAIL_TO recipients (comma-separated)",
    )
    parser.add_argument(
        "--skip-collect",
        action="store_true",
        help="Skip data collection (use existing articles in DB)",
    )
    parser.add_argument(
        "--skip-email",
        action="store_true",
        help="Skip email delivery (file output only)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable debug logging",
    )

    parser.set_defaults(mode="daily")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    start = datetime.now(tz=timezone.utc)
    logger.info("Pipeline started — mode=%s", args.mode)

    try:
        results = run_pipeline(
            mode=args.mode,
            db_path=args.db,
            output_dir=args.output_dir,
            email_to=args.email_to,
            skip_collect=args.skip_collect,
            skip_email=args.skip_email,
        )
    except Exception:
        logger.exception("Pipeline failed")
        return 1

    elapsed = (datetime.now(tz=timezone.utc) - start).total_seconds()

    # ── summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f" News Agent — {args.mode} run complete ({elapsed:.1f}s)")
    print(f"{'='*60}")

    if results["collected"]:
        total_new = sum(results["collected"].values())
        print(f" Collected   : {total_new} new articles {results['collected']}")

    p = results["processed"]
    if p:
        print(
            f" Processed   : {p.get('extracted', 0)} extracted, "
            f"{p.get('scored', 0)} scored, {p.get('flagged', 0)} flagged"
        )

    print(f" Briefing    : {results['briefing_articles']} articles summarised")

    d = results["delivery"]
    if d.get("file"):
        print(f" Saved to    : {d['file']}")
    if d.get("email"):
        print(f" Emailed     : yes")
    else:
        print(f" Emailed     : no")

    print(f"{'='*60}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
