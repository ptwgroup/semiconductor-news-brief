from datetime import UTC, datetime

from semibrief.util import (
    canonicalize_url,
    headline_similarity,
    mask_email,
    parse_datetime,
)


def test_canonicalize_url_removes_tracking() -> None:
    result = canonicalize_url("HTTPS://WWW.Example.com/a/?utm_source=x&id=7#top")
    assert result == "https://example.com/a?id=7"


def test_parse_gdelt_datetime() -> None:
    assert parse_datetime("20260727T001500Z") == datetime(2026, 7, 27, 0, 15, tzinfo=UTC)


def test_headline_similarity() -> None:
    assert (
        headline_similarity(
            "TSMC expands advanced packaging capacity",
            "TSMC to expand its advanced packaging capacity",
        )
        >= 0.6
    )


def test_mask_email() -> None:
    assert mask_email("alice@example.com") == "a***@example.com"
