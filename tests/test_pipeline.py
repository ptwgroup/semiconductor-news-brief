from datetime import UTC, datetime, timedelta
from pathlib import Path

from semibrief.config import Settings
from semibrief.pipeline import Pipeline, run_lock


def settings(tmp_path: Path) -> Settings:
    config = tmp_path / "config"
    config.mkdir()
    (config / "sources.yml").write_text(
        "publishers: []\ndirect_feeds: []\ndiscovery: {}\nlinkedin: {enabled: false}\n"
    )
    (config / "interests.yml").write_text("maximum_stories: 10\n")
    return Settings(
        timezone="Asia/Singapore",
        database_path=tmp_path / "data.sqlite3",
        output_dir=tmp_path / "out",
        config_dir=config,
        http_timeout=1,
        user_agent="test",
        libretranslate_url=None,
        libretranslate_api_key=None,
    )


def test_first_window_is_24_hours(tmp_path) -> None:
    pipeline = Pipeline(settings(tmp_path))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    start, end = pipeline.coverage_window(now)
    assert end - start == timedelta(hours=24)


def test_later_window_overlaps_two_hours(tmp_path) -> None:
    pipeline = Pipeline(settings(tmp_path))
    success = datetime(2026, 7, 26, 23, tzinfo=UTC)
    pipeline.db.mark_success(success)
    start, _ = pipeline.coverage_window(datetime(2026, 7, 27, tzinfo=UTC))
    assert start == success - timedelta(hours=2)


def test_dry_run_is_repeatable(tmp_path) -> None:
    pipeline = Pipeline(settings(tmp_path))
    now = datetime(2026, 7, 27, tzinfo=UTC)
    first = pipeline.run(now, dry_run=True)
    second = pipeline.run(now, dry_run=True)
    assert first == second
    assert first.exists()
    assert pipeline.db.last_success() is None


def test_lock_rejects_overlap(tmp_path) -> None:
    path = tmp_path / "run.lock"
    with run_lock(path):
        try:
            with run_lock(path):
                raise AssertionError("nested lock should fail")
        except RuntimeError:
            pass
