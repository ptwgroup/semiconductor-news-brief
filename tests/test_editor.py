from datetime import UTC, datetime, timedelta

from semibrief.editor import (
    apply_feedback,
    classify,
    deduplicate,
    extractive_bullets,
    prepare_articles,
    score_article,
)
from semibrief.models import Article

NOW = datetime(2026, 7, 27, 1, 0, tzinfo=UTC)


def article(title: str, url: str = "https://example.com/a") -> Article:
    return Article(
        title=title,
        url=url,
        source="Reuters",
        summary=(
            "The company will invest $5 billion in additional capacity. "
            "Production is expected to support high-bandwidth memory systems."
        ),
        published_at=NOW - timedelta(hours=1),
        source_priority=5,
    )


def test_classification() -> None:
    assert classify(article("ASML expands EUV equipment output")) == "Equipment"


def test_material_story_scores_high() -> None:
    item = article("TSMC invests $5 billion in new semiconductor fab capacity")
    score = score_article(
        item,
        NOW,
        {"priority_companies": ["TSMC"], "priority_topics": ["foundry"]},
    )
    assert score >= 10


def test_deduplicate_clusters_similar_headlines() -> None:
    first = article("TSMC expands advanced packaging capacity", "https://one.test/a")
    second = article("TSMC to expand its advanced packaging capacity", "https://two.test/b")
    first.score = 12
    second.score = 10
    result = deduplicate([first, second])
    assert len(result) == 1
    assert result[0].corroborating_urls == ["https://two.test/b"]


def test_prepare_assigns_fingerprint_and_impact() -> None:
    result = prepare_articles(
        [article("TSMC invests $5 billion in semiconductor fab capacity")],
        NOW,
        {"priority_companies": ["TSMC"]},
    )
    assert result[0].fingerprint
    assert result[0].impact in {"CRITICAL", "HIGH"}


def test_extractive_bullets_are_bounded() -> None:
    assert len(extractive_bullets(article("TSMC capacity expansion"))) <= 2


def test_feedback_adjusts_similar_story() -> None:
    item = article("TSMC expands packaging capacity")
    item.score = 8
    result = apply_feedback([item], [("TSMC plans packaging capacity expansion", "more_like_this")])
    assert result[0].score == 9.5
    assert result[0].impact == "HIGH"
