"""Comprehensive test suite for news-agent.

Covers: config, database (schema + migrations + dedup + queries),
extractor fallback logic, keyword scorer, delivery (file + email skip),
summarizer helpers, pipeline wiring, CLI arg parsing, and the
notify_slack script.

Run with:  python -m pytest tests/test_all.py -v
"""

import os
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


# ═══════════════════════════════════════════════════════════════════════════
#  Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_db(tmp_path):
    """Return the path to a fresh temp database, already initialised."""
    from data_collector.database import init_db
    db = str(tmp_path / "test.db")
    init_db(db)
    return db


@pytest.fixture
def tmp_output(tmp_path):
    return str(tmp_path / "output")


# ═══════════════════════════════════════════════════════════════════════════
#  Config
# ═══════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_config_imports(self):
        from data_collector.config import (
            DATABASE_PATH, RSS_FEEDS, SUBREDDITS, HN_KEYWORDS,
            SUMMARY_OUTPUT_DIR, OUTPUT_DIR,
            EMAIL_BACKEND, SMTP_HOST, SENDGRID_API_KEY,
        )
        assert isinstance(RSS_FEEDS, list) and len(RSS_FEEDS) > 0
        assert isinstance(SUBREDDITS, list) and len(SUBREDDITS) > 0
        assert isinstance(HN_KEYWORDS, list) and len(HN_KEYWORDS) > 0

    def test_env_overrides(self):
        """Config values fall back to defaults when env vars are unset."""
        from data_collector.config import DATABASE_PATH
        assert DATABASE_PATH  # should have a default


# ═══════════════════════════════════════════════════════════════════════════
#  Database
# ═══════════════════════════════════════════════════════════════════════════

class TestDatabase:
    def test_init_creates_table(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        assert ("articles",) in tables
        conn.close()

    def test_schema_has_all_columns(self, tmp_db):
        conn = sqlite3.connect(tmp_db)
        info = conn.execute("PRAGMA table_info(articles)").fetchall()
        col_names = {row[1] for row in info}
        expected = {
            "id", "title", "source", "url", "published_date",
            "raw_text", "extracted_text", "relevance_score",
            "processed", "created_at",
        }
        assert expected == col_names
        conn.close()

    def test_insert_and_dedup(self, tmp_db):
        from data_collector.database import get_connection, insert_article
        with get_connection(tmp_db) as conn:
            assert insert_article(conn, "T1", "src", "http://a.com/1") is True
            assert insert_article(conn, "T1 dup", "src", "http://a.com/1") is False
            assert insert_article(conn, "T2", "src", "http://a.com/2") is True

    def test_count_articles(self, tmp_db):
        from data_collector.database import get_connection, insert_article, count_articles
        with get_connection(tmp_db) as conn:
            insert_article(conn, "A", "s", "http://x.com/1")
            insert_article(conn, "B", "s", "http://x.com/2")
        assert count_articles(tmp_db) == 2

    def test_unprocessed_query(self, tmp_db):
        from data_collector.database import (
            get_connection, insert_article, get_unprocessed_articles,
        )
        with get_connection(tmp_db) as conn:
            insert_article(conn, "A", "s", "http://x.com/1")
            rows = get_unprocessed_articles(conn)
            assert len(rows) == 1
            assert rows[0][1] == "A"  # title

    def test_update_extracted_text(self, tmp_db):
        from data_collector.database import (
            get_connection, insert_article, update_extracted_text,
        )
        with get_connection(tmp_db) as conn:
            insert_article(conn, "A", "s", "http://x.com/1")
            update_extracted_text(conn, 1, "full body")
            row = conn.execute(
                "SELECT extracted_text FROM articles WHERE id=1"
            ).fetchone()
            assert row[0] == "full body"

    def test_relevance_score_high_stays_unprocessed(self, tmp_db):
        from data_collector.database import (
            get_connection, insert_article, update_relevance_score,
        )
        with get_connection(tmp_db) as conn:
            insert_article(conn, "A", "s", "http://x.com/1")
            update_relevance_score(conn, 1, 4, mark_processed=True)
            row = conn.execute("SELECT processed FROM articles WHERE id=1").fetchone()
            assert row[0] == 0  # stays unprocessed for summariser

    def test_relevance_score_low_marks_processed(self, tmp_db):
        from data_collector.database import (
            get_connection, insert_article, update_relevance_score,
        )
        with get_connection(tmp_db) as conn:
            insert_article(conn, "A", "s", "http://x.com/1")
            update_relevance_score(conn, 1, 2, mark_processed=True)
            row = conn.execute("SELECT processed FROM articles WHERE id=1").fetchone()
            assert row[0] == 1

    def test_summarization_query_time_filter(self, tmp_db):
        from data_collector.database import (
            get_connection, get_articles_for_summarization,
        )
        now = datetime.now(tz=timezone.utc)
        recent = (now - timedelta(hours=2)).isoformat()
        old = (now - timedelta(days=3)).isoformat()
        cutoff = (now - timedelta(hours=24)).isoformat()

        with get_connection(tmp_db) as conn:
            conn.execute(
                """INSERT INTO articles
                   (title,source,url,published_date,extracted_text,
                    relevance_score,processed,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("Recent", "s", "http://r.com", recent, "txt", 4, 0, recent),
            )
            conn.execute(
                """INSERT INTO articles
                   (title,source,url,published_date,extracted_text,
                    relevance_score,processed,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("Old", "s", "http://o.com", old, "txt", 5, 0, old),
            )
            # Daily: only the recent one
            daily = get_articles_for_summarization(conn, since=cutoff)
            assert len(daily) == 1
            assert daily[0]["title"] == "Recent"

            # No filter: both
            all_arts = get_articles_for_summarization(conn, since=None)
            assert len(all_arts) == 2

    def test_summarization_query_returns_dicts(self, tmp_db):
        from data_collector.database import get_connection, get_articles_for_summarization
        now = datetime.now(tz=timezone.utc).isoformat()
        with get_connection(tmp_db) as conn:
            conn.execute(
                """INSERT INTO articles
                   (title,source,url,published_date,extracted_text,
                    relevance_score,processed,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("X", "s", "http://x.com", now, "txt", 3, 0, now),
            )
            results = get_articles_for_summarization(conn, since=None)
            assert isinstance(results[0], dict)
            for key in ("id", "title", "source", "url", "extracted_text", "relevance_score"):
                assert key in results[0]

    def test_mark_articles_processed_bulk(self, tmp_db):
        from data_collector.database import (
            get_connection, mark_articles_processed,
            get_articles_for_summarization,
        )
        now = datetime.now(tz=timezone.utc).isoformat()
        with get_connection(tmp_db) as conn:
            for i in range(3):
                conn.execute(
                    """INSERT INTO articles
                       (title,source,url,published_date,extracted_text,
                        relevance_score,processed,created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (f"Art{i}", "s", f"http://x.com/{i}", now, "t", 4, 0, now),
                )
            mark_articles_processed(conn, [1, 2, 3])
            remaining = get_articles_for_summarization(conn, since=None)
            assert len(remaining) == 0

    def test_migration_idempotent(self, tmp_db):
        """Running init_db twice doesn't crash."""
        from data_collector.database import init_db
        init_db(tmp_db)
        init_db(tmp_db)


# ═══════════════════════════════════════════════════════════════════════════
#  Extractor
# ═══════════════════════════════════════════════════════════════════════════

class TestExtractor:
    def test_fallback_to_raw_text(self):
        """When both extractors fail, falls back to existing raw text."""
        from data_collector.extractor import extract_text
        with patch("data_collector.extractor.extract_with_trafilatura", return_value=None), \
             patch("data_collector.extractor.extract_with_newspaper", return_value=None):
            result = extract_text("http://fail.example.com", existing_raw="feed summary")
            assert result == "feed summary"

    def test_returns_none_when_everything_fails(self):
        from data_collector.extractor import extract_text
        with patch("data_collector.extractor.extract_with_trafilatura", return_value=None), \
             patch("data_collector.extractor.extract_with_newspaper", return_value=None):
            result = extract_text("http://fail.example.com", existing_raw=None)
            assert result is None

    def test_trafilatura_preferred(self):
        from data_collector.extractor import extract_text
        with patch("data_collector.extractor.extract_with_trafilatura", return_value="traf text"), \
             patch("data_collector.extractor.extract_with_newspaper", return_value="news text"):
            result = extract_text("http://example.com")
            assert result == "traf text"

    def test_newspaper_fallback(self):
        from data_collector.extractor import extract_text
        with patch("data_collector.extractor.extract_with_trafilatura", return_value=None), \
             patch("data_collector.extractor.extract_with_newspaper", return_value="news text"):
            result = extract_text("http://example.com")
            assert result == "news text"


# ═══════════════════════════════════════════════════════════════════════════
#  Scorer (keyword-based)
# ═══════════════════════════════════════════════════════════════════════════

class TestScorer:
    def test_no_keywords_returns_1(self):
        from data_collector.scorer import score_article
        assert score_article("Cooking recipes for beginners", "How to bake a cake") == 1

    def test_tier_2_body_match(self):
        from data_collector.scorer import score_article
        score = score_article("Tech news today", "Intel released a new chip for servers")
        assert score == 2

    def test_tier_3_body_match(self):
        from data_collector.scorer import score_article
        score = score_article("Industry update", "The new datacenter opened in Virginia")
        assert score == 3

    def test_tier_4_body_match(self):
        from data_collector.scorer import score_article
        score = score_article(
            "Industry update",
            "The company announced new 800G optical transceiver modules"
        )
        assert score == 4

    def test_tier_5_body_match(self):
        from data_collector.scorer import score_article
        score = score_article(
            "Research paper released",
            "Advances in silicon photonics for datacenter interconnects"
        )
        assert score == 5

    def test_title_match_boosts_score(self):
        from data_collector.scorer import score_article
        # "datacenter" in title is tier 3 -> boosted to 4
        score = score_article("New datacenter opens in Texas", "The facility is large")
        assert score == 4

    def test_title_match_tier_5_caps_at_5(self):
        from data_collector.scorer import score_article
        score = score_article("Silicon photonics breakthrough", "Details of the research")
        assert score == 5  # tier 5 in title, boost would be 6 but capped

    def test_highest_tier_wins(self):
        from data_collector.scorer import score_article
        # Has tier 2 ("nvidia") and tier 5 ("silicon photonics") — should get 5
        score = score_article(
            "Industry news",
            "Nvidia invests in silicon photonics research for next-gen interconnects"
        )
        assert score == 5

    def test_empty_text_still_scores_title(self):
        from data_collector.scorer import score_article
        score = score_article("Optical interconnect update", "")
        assert score == 5  # tier 4 in title -> boosted to 5

    def test_case_insensitive(self):
        from data_collector.scorer import score_article
        score = score_article("SILICON PHOTONICS NEWS", "big announcement")
        assert score == 5


# ═══════════════════════════════════════════════════════════════════════════
#  Delivery
# ═══════════════════════════════════════════════════════════════════════════

class TestDelivery:
    def test_save_to_file(self, tmp_output):
        from data_collector.delivery import save_to_file
        path = save_to_file("# Briefing\nContent", mode="daily", output_dir=tmp_output)
        assert os.path.isfile(path)
        assert "briefing_daily_" in os.path.basename(path)
        with open(path) as f:
            assert "# Briefing" in f.read()

    def test_subject_line(self):
        from data_collector.delivery import _subject_line
        s = _subject_line("daily")
        assert "[News Agent]" in s
        assert "Daily" in s

    def test_recipient_list_parsing(self):
        from data_collector.delivery import _recipient_list
        assert _recipient_list("a@b.com, c@d.com") == ["a@b.com", "c@d.com"]
        assert _recipient_list("  x@y.com  ") == ["x@y.com"]
        assert _recipient_list("") == []

    def test_deliver_file_only(self, tmp_output):
        from data_collector.delivery import deliver
        result = deliver("text", mode="daily", output_dir=tmp_output)
        assert result["file"] is not None
        assert os.path.isfile(result["file"])
        assert result["email"] is False

    def test_deliver_skip_file(self):
        from data_collector.delivery import deliver
        result = deliver("text", skip_file=True)
        assert result["file"] is None

    def test_smtp_skips_without_creds(self):
        from data_collector.delivery import send_via_smtp
        assert send_via_smtp("text", email_to="x@y.com") is False

    def test_sendgrid_skips_without_key(self):
        from data_collector.delivery import send_via_sendgrid
        assert send_via_sendgrid("text", email_to="x@y.com") is False


# ═══════════════════════════════════════════════════════════════════════════
#  Summarizer helpers
# ═══════════════════════════════════════════════════════════════════════════

class TestSummarizer:
    def test_lookback_iso_daily(self):
        from data_collector.summarizer import _lookback_iso
        iso = _lookback_iso("daily")
        dt = datetime.fromisoformat(iso)
        assert (datetime.now(tz=timezone.utc) - dt).total_seconds() < 90000  # ~25h

    def test_lookback_iso_weekly(self):
        from data_collector.summarizer import _lookback_iso
        iso = _lookback_iso("weekly")
        dt = datetime.fromisoformat(iso)
        diff = (datetime.now(tz=timezone.utc) - dt).total_seconds()
        assert 6 * 86400 < diff < 8 * 86400

    def test_categorize_datacenter_networking(self):
        from data_collector.summarizer import _categorize_article
        art = {"title": "New spine-leaf deployment", "extracted_text": "network fabric upgrade"}
        assert _categorize_article(art) == "Datacenter Networking"

    def test_categorize_hardware(self):
        from data_collector.summarizer import _categorize_article
        art = {"title": "800G transceiver launch", "extracted_text": "silicon photonics module"}
        assert _categorize_article(art) == "Hardware & Interconnects"

    def test_categorize_ai_demand(self):
        from data_collector.summarizer import _categorize_article
        art = {"title": "GPU cluster expansion", "extracted_text": "ai infrastructure nvlink"}
        assert _categorize_article(art) == "AI Demand Signals"

    def test_categorize_fallback(self):
        from data_collector.summarizer import _categorize_article
        art = {"title": "Misc tech news", "extracted_text": "something unrelated"}
        assert _categorize_article(art) == "Worth Watching"

    def test_build_briefing_text_structure(self):
        from data_collector.summarizer import _build_briefing_text
        articles = [
            {"title": "T1", "source": "rss:x", "url": "http://a.com",
             "published_date": "2025-01-01", "extracted_text": "silicon photonics body",
             "relevance_score": 5, "id": 1},
            {"title": "T2", "source": "hackernews", "url": "http://b.com",
             "published_date": "2025-01-02", "extracted_text": "gpu cluster inference",
             "relevance_score": 4, "id": 2},
        ]
        text = _build_briefing_text(articles, "daily")
        assert "# News Agent" in text
        assert "## Top Stories" in text
        assert "## Datacenter Networking" in text
        assert "## Hardware & Interconnects" in text
        assert "## AI Demand Signals" in text
        assert "## Worth Watching" in text
        assert "http://a.com" in text
        assert "T1" in text

    def test_leading_text_truncation(self):
        from data_collector.summarizer import _leading_text
        long_body = "First sentence. " + "x" * 400
        art = {"extracted_text": long_body}
        result = _leading_text(art)
        assert len(result) <= 310  # 300 + "..."
        assert result.endswith("...") or result.endswith(".")

    def test_write_briefing(self, tmp_output):
        from data_collector.summarizer import _write_briefing
        path = _write_briefing("# Test", "weekly", tmp_output)
        assert os.path.isfile(path)
        assert "briefing_weekly_" in os.path.basename(path)

    def test_generate_briefing_empty_db(self, tmp_db, tmp_output):
        from data_collector.summarizer import generate_briefing
        result = generate_briefing(mode="daily", db_path=tmp_db, output_dir=tmp_output)
        assert result["articles_used"] == 0
        assert result["briefing_file"] is None
        assert result["briefing_text"] is None

    def test_generate_briefing_with_articles(self, tmp_db, tmp_output):
        from data_collector.database import get_connection
        from data_collector.summarizer import generate_briefing
        now = datetime.now(tz=timezone.utc).isoformat()
        with get_connection(tmp_db) as conn:
            conn.execute(
                """INSERT INTO articles
                   (title,source,url,published_date,extracted_text,
                    relevance_score,processed,created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                ("Test Article", "rss:x", "http://test.com", now,
                 "silicon photonics body text", 4, 0, now),
            )
        result = generate_briefing(mode="daily", db_path=tmp_db, output_dir=tmp_output)
        assert result["articles_used"] == 1
        assert result["briefing_file"] is not None
        assert os.path.isfile(result["briefing_file"])
        assert "Test Article" in result["briefing_text"]


# ═══════════════════════════════════════════════════════════════════════════
#  Pipeline (mocked)
# ═══════════════════════════════════════════════════════════════════════════

class TestPipeline:
    def test_process_empty_db(self, tmp_db):
        from data_collector.pipeline import process_articles
        stats = process_articles(db_path=tmp_db)
        assert stats == {"extracted": 0, "scored": 0, "flagged": 0, "skipped": 0}

    def test_process_with_mock_extraction_and_scoring(self, tmp_db):
        from data_collector.database import get_connection, insert_article
        from data_collector.pipeline import process_articles

        with get_connection(tmp_db) as conn:
            insert_article(conn, "Test", "src", "http://example.com/1", raw_text="raw")

        with patch("data_collector.pipeline.extract_text", return_value="extracted body"), \
             patch("data_collector.pipeline.score_article", return_value=4):
            stats = process_articles(db_path=tmp_db)

        assert stats["extracted"] == 1
        assert stats["scored"] == 1
        assert stats["flagged"] == 1
        assert stats["skipped"] == 0

    def test_process_skips_when_no_text(self, tmp_db):
        from data_collector.database import get_connection, insert_article
        from data_collector.pipeline import process_articles

        with get_connection(tmp_db) as conn:
            insert_article(conn, "Empty", "src", "http://example.com/empty")

        with patch("data_collector.pipeline.extract_text", return_value=None):
            stats = process_articles(db_path=tmp_db)

        assert stats["skipped"] == 1
        assert stats["extracted"] == 0


# ═══════════════════════════════════════════════════════════════════════════
#  CLI entry points
# ═══════════════════════════════════════════════════════════════════════════

class TestCLI:
    def test_main_py_help(self):
        r = subprocess.run(
            ["python3", "main.py", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        for flag in ("--daily", "--weekly", "--skip-collect", "--skip-email",
                     "--output-dir", "--email-to", "--db"):
            assert flag in r.stdout

    def test_collector_help(self):
        r = subprocess.run(
            ["python3", "-m", "data_collector.collector", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        for flag in ("--process", "--process-only", "--summarize",
                     "--summarize-only", "--mode"):
            assert flag in r.stdout

    def test_notify_slack_help(self):
        r = subprocess.run(
            ["python3", "scripts/notify_slack.py", "--help"],
            capture_output=True, text=True,
        )
        assert r.returncode == 0
        assert "--failure" in r.stdout
        assert "--success" in r.stdout


# ═══════════════════════════════════════════════════════════════════════════
#  Slack notifier
# ═══════════════════════════════════════════════════════════════════════════

class TestSlackNotifier:
    def test_payload_failure(self):
        from scripts.notify_slack import _build_failure_payload
        p = _build_failure_payload("http://example.com/run/1")
        assert "failed" in p["text"].lower()
        assert "http://example.com/run/1" in str(p)

    def test_payload_success(self):
        from scripts.notify_slack import _build_success_payload
        p = _build_success_payload("http://example.com/run/2")
        assert "succeeded" in p["text"].lower() or "delivered" in str(p).lower()
        assert "http://example.com/run/2" in str(p)

    def test_graceful_skip_no_webhook(self):
        """Exits 0 when SLACK_WEBHOOK_URL is not set."""
        env = {k: v for k, v in os.environ.items()}
        env.pop("SLACK_WEBHOOK_URL", None)
        r = subprocess.run(
            ["python3", "scripts/notify_slack.py", "--success", "--run-url", "http://x"],
            capture_output=True, text=True, env=env,
        )
        assert r.returncode == 0
