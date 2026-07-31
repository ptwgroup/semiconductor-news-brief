from datetime import UTC, datetime

from semibrief.models import Article
from semibrief.render import build_brief


def test_render_is_english_email_with_safe_html() -> None:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    item = Article(
        title="TSMC expands <capacity> & output",
        url="https://example.com/a?x=1&y=2",
        source="Reuters",
        summary="TSMC announced a material semiconductor capacity expansion.",
        published_at=now,
        score=12,
        impact="HIGH",
        tag="Foundry",
    )
    brief = build_brief([item], now, now, "Asia/Singapore", 20, 100)
    assert brief.subject == "Daily Semiconductor News Brief — 2026-07-27"
    assert "<capacity>" not in brief.html
    assert "&lt;capacity&gt;" in brief.html
    assert "Exactly" not in brief.plain_text
    assert brief.plain_text.count("EXECUTIVE TAKEAWAYS") == 1


def test_unverified_linkedin_goes_to_radar() -> None:
    now = datetime(2026, 7, 27, tzinfo=UTC)
    item = Article(
        title="Analyst flags possible fab delay",
        url="https://linkedin.com/posts/example",
        source="LinkedIn — Analyst",
        summary="An analyst said a delay may occur.",
        published_at=now,
        score=8,
        impact="WATCH",
        tag="Foundry",
        is_linkedin=True,
        linkedin_official=False,
    )
    brief = build_brief([item], now, now, "Asia/Singapore", 1, 1)
    assert "LinkedIn signal — not independently confirmed" in brief.plain_text


def test_render_has_packaging_and_front_end_sections() -> None:
    now = datetime(2026, 7, 31, tzinfo=UTC)
    items = [
        Article(
            title="Fan-out RDL process reduces package warpage",
            url="https://packaging.test/a",
            source="Packaging Source",
            summary="The process reduces warpage and improves assembly yield.",
            published_at=now,
            tag="Packaging Technology",
        ),
        Article(
            title="Wafer cleaning update improves process control",
            url="https://front-end.test/a",
            source="Front-End Source",
            summary="The wet clean update reduces defects on mature-node wafers.",
            published_at=now,
            tag="Front-End Process",
        ),
    ]
    brief = build_brief(items, now, now, "Asia/Singapore", 2, 2)
    assert "ADVANCED PACKAGING — 2–3 TECHNOLOGY UPDATES" in brief.plain_text
    assert "SEMICONDUCTOR TECHNOLOGY — 2–3 UPDATES" in brief.plain_text
    assert brief.plain_text.index("ADVANCED PACKAGING") < brief.plain_text.index(
        "SEMICONDUCTOR TECHNOLOGY"
    )
