"""SQLite state for BeriPost.

Three jobs:
  1. Remember which news articles we have already seen (never post twice).
  2. Remember trivia/dad-joke text we have already used (avoid repeats).
  3. Store the post queue (pending / approved / rejected / published) that the
     web app shows you.

SQLite is a single file at data/beripost.db. No server to run.
"""
from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    guid       TEXT UNIQUE NOT NULL,   -- stable id for the article (link or feed id)
    url        TEXT,
    title      TEXT,
    source     TEXT,
    first_seen REAL,
    used       INTEGER DEFAULT 0       -- 1 once we have built a post from it
);

CREATE TABLE IF NOT EXISTS light_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    kind       TEXT,                   -- 'trivia' or 'dad_joke'
    text_hash  TEXT UNIQUE,
    text       TEXT,
    created_at REAL
);

CREATE TABLE IF NOT EXISTS posts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    pillar       TEXT,                 -- news / education / trivia / dad_joke
    status       TEXT DEFAULT 'pending', -- published / failed
    headline     TEXT,
    body         TEXT,
    source_url   TEXT,
    image_path   TEXT,
    created_at   REAL,
    published_at REAL,
    fb_post_id   TEXT,
    error        TEXT
);

CREATE TABLE IF NOT EXISTS ingested_feedback (
    issue_id   INTEGER UNIQUE,         -- GitHub issue we have already folded in
    at         REAL
);
"""


class DB:
    def __init__(self, path: Path):
        self.path = str(path)
        self._init()

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- article dedup ------------------------------------------------------
    def article_seen(self, guid: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT 1 FROM articles WHERE guid = ?", (guid,)).fetchone()
            return row is not None

    def remember_article(self, guid: str, url: str, title: str, source: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO articles (guid, url, title, source, first_seen) "
                "VALUES (?, ?, ?, ?, ?)",
                (guid, url, title, source, time.time()),
            )

    def mark_article_used(self, guid: str, url: str = "", title: str = "", source: str = "") -> None:
        """Record an article as posted (upsert), so it is never posted again."""
        with self._conn() as c:
            c.execute(
                "INSERT INTO articles (guid, url, title, source, first_seen, used) "
                "VALUES (?, ?, ?, ?, ?, 1) "
                "ON CONFLICT(guid) DO UPDATE SET used = 1",
                (guid, url, title, source, time.time()),
            )

    # --- light content dedup ------------------------------------------------
    @staticmethod
    def _hash(text: str) -> str:
        norm = " ".join(text.lower().split())
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def light_seen(self, text: str) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM light_history WHERE text_hash = ?", (self._hash(text),)
            ).fetchone()
            return row is not None

    def remember_light(self, kind: str, text: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO light_history (kind, text_hash, text, created_at) "
                "VALUES (?, ?, ?, ?)",
                (kind, self._hash(text), text, time.time()),
            )

    # --- post queue ---------------------------------------------------------
    def add_post(
        self,
        pillar: str,
        headline: str,
        body: str,
        source_url: str | None = None,
        image_path: str | None = None,
        status: str = "pending",
    ) -> int:
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO posts (pillar, status, headline, body, source_url, image_path, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (pillar, status, headline, body, source_url, image_path, time.time()),
            )
            return int(cur.lastrowid)

    def get_post(self, post_id: int) -> dict | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
            return dict(row) if row else None

    def list_posts(self, status: str | None = None) -> list[dict]:
        with self._conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM posts WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM posts ORDER BY created_at DESC"
                ).fetchall()
            return [dict(r) for r in rows]

    def update_post(self, post_id: int, **fields) -> None:
        if not fields:
            return
        cols = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as c:
            c.execute(
                f"UPDATE posts SET {cols} WHERE id = ?",
                (*fields.values(), post_id),
            )

    def mark_published(self, post_id: int, fb_post_id: str) -> None:
        self.update_post(
            post_id, status="published", fb_post_id=fb_post_id, published_at=time.time(), error=None
        )

    def mark_failed(self, post_id: int, error: str) -> None:
        self.update_post(post_id, status="failed", error=error)

    # --- feedback issue tracking --------------------------------------------
    def feedback_issue_seen(self, issue_id: int) -> bool:
        with self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM ingested_feedback WHERE issue_id = ?", (issue_id,)
            ).fetchone()
            return row is not None

    def remember_feedback_issue(self, issue_id: int) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO ingested_feedback (issue_id, at) VALUES (?, ?)",
                (issue_id, time.time()),
            )
