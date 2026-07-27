from datetime import UTC, datetime

from semibrief.database import Database
from semibrief.models import Article


def test_success_and_sent_article_round_trip(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    now = datetime(2026, 7, 27, tzinfo=UTC)
    item = Article(
        title="Test",
        url="https://example.com",
        source="Test",
        published_at=now,
        fingerprint="abc",
    )
    database.mark_success(now)
    database.record_articles([item], now)
    database.set_feedback("abc", "more_like_this")
    assert database.last_success() == now
    assert database.was_sent("abc")
    assert database.feedback_rules() == [("Test", "more_like_this")]


def test_feedback_validation(tmp_path) -> None:
    database = Database(tmp_path / "test.sqlite3")
    database.initialize()
    database.set_feedback("abc", "more_like_this")
    try:
        database.set_feedback("abc", "unsupported")
    except ValueError:
        pass
    else:
        raise AssertionError("invalid feedback should fail")
