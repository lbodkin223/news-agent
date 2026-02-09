"""SQLite database layer for storing collected articles."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from data_collector.config import DATABASE_PATH

SCHEMA = """\
CREATE TABLE IF NOT EXISTS articles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    source      TEXT    NOT NULL,
    url         TEXT    NOT NULL UNIQUE,
    published_date TEXT,
    raw_text    TEXT,
    processed   INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url);
CREATE INDEX IF NOT EXISTS idx_articles_processed ON articles(processed);
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
"""


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
    """Create tables and indexes if they don't exist."""
    with get_connection(db_path) as conn:
        conn.executescript(SCHEMA)


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


def count_articles(db_path: Optional[str] = None) -> int:
    """Return total article count."""
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) FROM articles").fetchone()
        return row[0]
