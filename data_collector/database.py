"""SQLite database layer for storing collected articles."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from data_collector.config import DATABASE_PATH

SCHEMA = """\
CREATE TABLE IF NOT EXISTS articles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    url             TEXT    NOT NULL UNIQUE,
    published_date  TEXT,
    raw_text        TEXT,
    extracted_text  TEXT,
    relevance_score INTEGER,
    processed       INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_articles_processed ON articles(processed);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
"""

MIGRATIONS = [
    "ALTER TABLE articles ADD COLUMN extracted_text TEXT",
    "ALTER TABLE articles ADD COLUMN relevance_score INTEGER",
]


@contextmanager
def get_connection(db_path: Optional[str] = None):
    """Yield a SQLite connection that commits on success and rolls back on error."""
    conn = sqlite3.connect(db_path or DATABASE_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[str] = None):
    """Create tables and indexes if they don't exist.

    Also applies column migrations for older databases that lack
    the extracted_text / relevance_score columns.
    """
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                # Column already exists — safe to ignore.
                pass


def insert_article(
    conn: sqlite3.Connection,
    title: str,
    source: str,
    url: str,
    published_date: Optional[str] = None,
    raw_text: Optional[str] = None,
) -> bool:
    """Insert an article, skipping duplicates by URL.

    Returns True if the row was inserted, False if it already existed.
    """
    try:
        conn.execute(
            """
            INSERT INTO articles (title, source, url, published_date, raw_text, processed, created_at)
            VALUES (?, ?, ?, ?, ?, 0, ?)
            """,
            (title, source, url, published_date, raw_text, datetime.utcnow().isoformat()),
        )
        return True
    except sqlite3.IntegrityError:
        # Duplicate URL — skip silently.
        return False


def get_unprocessed_articles(
    conn: sqlite3.Connection,
) -> list[tuple[int, str, str, str | None]]:
    """Return (id, title, url, raw_text) for articles not yet processed."""
    rows = conn.execute(
        "SELECT id, title, url, raw_text FROM articles WHERE processed = 0"
    ).fetchall()
    return rows


def update_extracted_text(conn: sqlite3.Connection, article_id: int, text: str):
    """Store extracted body text for an article."""
    conn.execute(
        "UPDATE articles SET extracted_text = ? WHERE id = ?",
        (text, article_id),
    )


def update_relevance_score(
    conn: sqlite3.Connection, article_id: int, score: int, mark_processed: bool = True
):
    """Store relevance score (1-5).  If score >= 3, keep processed=0 so it gets
    picked up for summarization.  Otherwise mark processed=1 (done)."""
    if mark_processed:
        processed_flag = 0 if score >= 3 else 1
    else:
        processed_flag = 0
    conn.execute(
        "UPDATE articles SET relevance_score = ?, processed = ? WHERE id = ?",
        (score, processed_flag, article_id),
    )


def mark_processed(conn: sqlite3.Connection, article_id: int):
    """Set processed = 1 for the given article."""
    conn.execute("UPDATE articles SET processed = 1 WHERE id = ?", (article_id,))


def get_articles_for_summarization(
    conn: sqlite3.Connection,
) -> list[tuple[int, str, str, str | None, int]]:
    """Return articles scored 3+ that are still awaiting summarization.

    Returns (id, title, url, extracted_text, relevance_score).
    """
    return conn.execute(
        """SELECT id, title, url, extracted_text, relevance_score
           FROM articles
           WHERE relevance_score >= 3 AND processed = 0"""
    ).fetchall()


def count_articles(db_path: Optional[str] = None) -> int:
    """Return total article count."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        return row[0]
