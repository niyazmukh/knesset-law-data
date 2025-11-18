import sqlite3
import os
from datetime import datetime
from typing import Optional, Tuple

import config  # type: ignore


_DDL = """
CREATE TABLE IF NOT EXISTS downloads (
  url TEXT PRIMARY KEY,
  filename TEXT,
  size_bytes INTEGER,
  sha256 TEXT,
  content_type TEXT,
  http_status INTEGER,
  status TEXT,              -- pending|success|failed
  attempts INTEGER DEFAULT 0,
  last_error TEXT,
  last_attempt_at TEXT
);
"""


def _conn():
    os.makedirs(os.path.dirname(config.STATE_DB), exist_ok=True)
    conn = sqlite3.connect(config.STATE_DB)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    with _conn() as c:
        c.execute(_DDL)


def get_download(url: str) -> Optional[Tuple]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM downloads WHERE url=?", (url,))
        return cur.fetchone()


def mark_attempt(url: str):
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        row = get_download(url)
        if row:
            c.execute(
                "UPDATE downloads SET attempts = COALESCE(attempts,0)+1, last_attempt_at=?, status=? WHERE url=?",
                (now, "pending", url),
            )
        else:
            c.execute(
                "INSERT INTO downloads(url, status, attempts, last_attempt_at) VALUES(?,?,?,?)",
                (url, "pending", 1, now),
            )


def mark_success(
    url: str,
    filename: str,
    size_bytes: int,
    sha256: str,
    content_type: str,
    http_status: int,
):
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        c.execute(
            """
            INSERT INTO downloads(url, filename, size_bytes, sha256, content_type, http_status, status, attempts, last_attempt_at)
            VALUES(?,?,?,?,?,?,?,1,?)
            ON CONFLICT(url) DO UPDATE SET
              filename=excluded.filename,
              size_bytes=excluded.size_bytes,
              sha256=excluded.sha256,
              content_type=excluded.content_type,
              http_status=excluded.http_status,
              status='success',
                            last_error=NULL,
                            last_attempt_at=excluded.last_attempt_at
            """,
            (url, filename, size_bytes, sha256, content_type, http_status, "success", now),
        )


def mark_failure(url: str, last_error: str, http_status: Optional[int] = None):
    now = datetime.utcnow().isoformat()
    with _conn() as c:
        row = get_download(url)
        if row:
            c.execute(
                "UPDATE downloads SET status=?, last_error=?, http_status=COALESCE(?, http_status), last_attempt_at=? WHERE url=?",
                ("failed", last_error[:2000], http_status, now, url),
            )
        else:
            c.execute(
                "INSERT INTO downloads(url, status, last_error, http_status, attempts, last_attempt_at) VALUES(?,?,?,?,?,?)",
                (url, "failed", last_error[:2000], http_status, 1, now),
            )


def is_success(url: str) -> bool:
    with _conn() as c:
        cur = c.execute("SELECT 1 FROM downloads WHERE url=? AND status='success'", (url,))
        return cur.fetchone() is not None
