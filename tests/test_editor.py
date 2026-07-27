from datetime import UTC, datetime, timedelta

from semibrief.editor import (
    apply_feedback,
    classify,
    deduplicate,
    extractive_bullets,
    prepare_articles,
    score_article,
    select_balanced,
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


def test_specialty_classification() -> None:
    assert classify(article("New 200mm SiC power semiconductor fab ramps")) == "Power Devices"
    assert classify(article("MEMS pressure sensor capacity expands")) == "MEMS & Sensors"
    assert classify(article("Foundry adds 180nm BCD process")) == "Mature Nodes"


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


def test_balanced_selection_protects_specialty_coverage() -> None:
    items = []
    for index in range(7):
        item = article(f"AI GPU HBM story {index}", f"https://leading.test/{index}")
        item.fingerprint = f"leading-{index}"
        item.tag = "AI Chips"
        item.score = 20 - index
        items.append(item)
    for index in range(6):
        item = article(
            f"180nm analog MEMS customer story {index}",
            f"https://specialty.test/{index}",
        )
        item.fingerprint = f"specialty-{index}"
        item.tag = "Mature Nodes"
        item.score = 10 - index
        items.append(item)
    result = select_balanced(items, 10, 6, 3)
    assert sum(item.tag == "Mature Nodes" for item in result) == 6
    assert sum(item.tag == "AI Chips" for item in result) == 4
