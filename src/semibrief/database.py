from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import Article


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def session(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.session() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sent_articles (
                    fingerprint TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    url TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS briefs (
                    idempotency_key TEXT PRIMARY KEY,
                    subject TEXT NOT NULL,
                    window_start TEXT NOT NULL,
                    window_end TEXT NOT NULL,
                    path TEXT NOT NULL,
                    sent_at TEXT
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    fingerprint TEXT PRIMARY KEY,
                    preference TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def last_success(self) -> datetime | None:
        with self.session() as connection:
            row = connection.execute(
                "SELECT value FROM state WHERE key = 'last_success'"
            ).fetchone()
        return datetime.fromisoformat(row["value"]) if row else None

    def mark_success(self, when: datetime) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO state(key, value) VALUES('last_success', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (when.astimezone(UTC).isoformat(),),
            )

    def was_sent(self, article_fingerprint: str) -> bool:
        with self.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM sent_articles WHERE fingerprint = ?",
                (article_fingerprint,),
            ).fetchone()
        return row is not None

    def record_articles(self, articles: list[Article], sent_at: datetime) -> None:
        with self.session() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO sent_articles(fingerprint, title, url, sent_at)
                VALUES(?, ?, ?, ?)
                """,
                [
                    (article.fingerprint, article.title, article.url, sent_at.isoformat())
                    for article in articles
                ],
            )

    def brief_exists(self, key: str) -> bool:
        with self.session() as connection:
            row = connection.execute(
                "SELECT 1 FROM briefs WHERE idempotency_key = ?", (key,)
            ).fetchone()
        return row is not None

    def record_brief(
        self,
        key: str,
        subject: str,
        start: datetime,
        end: datetime,
        path: Path,
        sent_at: datetime | None,
    ) -> None:
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO briefs(
                    idempotency_key, subject, window_start, window_end, path, sent_at
                ) VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    subject,
                    start.isoformat(),
                    end.isoformat(),
                    str(path),
                    sent_at.isoformat() if sent_at else None,
                ),
            )

    def set_feedback(self, article_fingerprint: str, preference: str) -> None:
        if preference not in {"more_like_this", "less_like_this", "irrelevant"}:
            raise ValueError("Unsupported preference")
        with self.session() as connection:
            connection.execute(
                """
                INSERT INTO feedback(fingerprint, preference, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(fingerprint) DO UPDATE SET
                    preference = excluded.preference,
                    updated_at = excluded.updated_at
                """,
                (article_fingerprint, preference, datetime.now(UTC).isoformat()),
            )

    def feedback_rules(self) -> list[tuple[str, str]]:
        with self.session() as connection:
            rows = connection.execute(
                """
                SELECT sent_articles.title, feedback.preference
                FROM feedback
                JOIN sent_articles USING(fingerprint)
                """
            ).fetchall()
        return [(str(row["title"]), str(row["preference"])) for row in rows]
