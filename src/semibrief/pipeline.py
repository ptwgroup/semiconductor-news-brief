from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from .config import Settings, load_yaml
from .database import Database
from .discovery import (
    fetch_feed,
    fetch_gdelt,
    fetch_linkedin_urls,
    google_news_url,
)
from .editor import (
    apply_feedback,
    prepare_articles,
    select_balanced,
    translate_if_needed,
)
from .mailer import send_brief
from .models import Article, Brief
from .render import build_brief

LOGGER = logging.getLogger(__name__)


@contextmanager
def run_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"Another run holds {path}") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        os.close(descriptor)
        yield
    finally:
        path.unlink(missing_ok=True)


class Pipeline:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db = Database(settings.database_path)
        self.db.initialize()
        self.sources = load_yaml(settings.config_dir / "sources.yml")
        self.interests = load_yaml(settings.config_dir / "interests.yml")

    def coverage_window(self, now: datetime) -> tuple[datetime, datetime]:
        last = self.db.last_success()
        start = (last - timedelta(hours=2)) if last else (now - timedelta(hours=24))
        return start.astimezone(UTC), now.astimezone(UTC)

    def collect(self, start: datetime, end: datetime) -> list[Article]:
        publishers = list(self.sources.get("publishers", []))
        regional_news = self.sources.get("regional_news", {})
        regional_source_names = {
            self._normalize_source(str(name)) for name in regional_news.get("sources", [])
        }
        regional_publishers = [
            publisher
            for publisher in publishers
            if self._normalize_source(str(publisher["name"])) in regional_source_names
        ]
        regional_start = end - timedelta(
            hours=max(24, int(regional_news.get("lookback_hours", 168)))
        )
        publisher_by_alias = {}
        for publisher in publishers:
            publisher_by_alias[self._normalize_source(str(publisher["name"]))] = publisher
            publisher_by_alias[self._normalize_source(str(publisher["domain"]))] = publisher
        trusted_sources = {self._normalize_source(str(item["name"])) for item in publishers} | {
            self._normalize_source(str(item["name"]))
            for item in self.sources.get("direct_feeds", [])
        }
        allow_unlisted = bool(
            self.sources.get("quality", {}).get("allow_unlisted_publishers", False)
        )
        discovery = self.sources.get("discovery", {})
        headers = {"User-Agent": self.settings.user_agent}
        articles = []
        with httpx.Client(
            headers=headers,
            timeout=self.settings.http_timeout,
            follow_redirects=True,
        ) as client:
            gdelt = discovery.get("gdelt", {})
            if gdelt.get("enabled", False):
                hours = max(1, int((end - start).total_seconds() / 3600) + 2)
                try:
                    articles.extend(fetch_gdelt(client, gdelt, publishers, hours))
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    LOGGER.warning("GDELT collection failed: %s", exc)
                if regional_publishers:
                    regional_gdelt = dict(gdelt)
                    domains = " OR ".join(
                        f"domain:{publisher['domain']}" for publisher in regional_publishers
                    )
                    regional_gdelt["query"] = f"({gdelt['query']}) AND ({domains})"
                    regional_hours = max(
                        hours,
                        int((end - regional_start).total_seconds() / 3600) + 2,
                    )
                    try:
                        articles.extend(
                            fetch_gdelt(
                                client,
                                regional_gdelt,
                                regional_publishers,
                                regional_hours,
                            )
                        )
                    except (httpx.HTTPError, ValueError, KeyError) as exc:
                        LOGGER.warning("Regional GDELT collection failed: %s", exc)
            google = discovery.get("google_news", {})
            if google.get("enabled", False):
                for query in google.get("queries", []):
                    try:
                        url = google_news_url(
                            str(query),
                            str(google.get("language", "en")),
                            str(google.get("country", "SG")),
                        )
                        articles.extend(fetch_feed(client, url, "Google News", "Global", 2))
                    except (httpx.HTTPError, ValueError) as exc:
                        LOGGER.warning("Google News query failed: %s", exc)
            if regional_publishers and regional_news.get("google_news_fallback", True):
                sites = " OR ".join(
                    f"site:{publisher['domain']}" for publisher in regional_publishers
                )
                hours = max(24, int(regional_news.get("lookback_hours", 168)))
                days = max(1, (hours + 23) // 24)
                query = (
                    f"({sites}) (semiconductor OR chipmaker OR wafer fab OR MEMS "
                    f'OR "power semiconductor" OR packaging) when:{days}d'
                )
                try:
                    url = google_news_url(query, "en", "SG")
                    articles.extend(fetch_feed(client, url, "Google News Regional", "Global", 4))
                except (httpx.HTTPError, ValueError) as exc:
                    LOGGER.warning("Regional Google News collection failed: %s", exc)
            for feed in self.sources.get("direct_feeds", []):
                try:
                    articles.extend(
                        fetch_feed(
                            client,
                            str(feed["url"]),
                            str(feed["name"]),
                            str(feed.get("region", "Global")),
                            int(feed.get("priority", 3)),
                        )
                    )
                except (httpx.HTTPError, ValueError, KeyError) as exc:
                    LOGGER.warning("Feed %s failed: %s", feed.get("name"), exc)
            linkedin = self.sources.get("linkedin", {})
            if linkedin.get("enabled", False):
                path = self.settings.config_dir / str(
                    linkedin.get("urls_file", "linkedin_urls.yml")
                )
                articles.extend(fetch_linkedin_urls(client, path, end))

            translated = []
            for article in articles:
                normalized_source = self._normalize_source(article.source)
                publisher = publisher_by_alias.get(normalized_source)
                if publisher is not None:
                    article.source = str(publisher["name"])
                    article.region = str(publisher.get("region", "Global"))
                    article.source_priority = max(
                        article.source_priority,
                        int(publisher.get("priority", 3)),
                    )
                    normalized_source = self._normalize_source(article.source)
                article_start = (
                    regional_start if normalized_source in regional_source_names else start
                )
                if not (article_start <= article.published_at <= end + timedelta(minutes=5)):
                    continue
                try:
                    result = translate_if_needed(
                        article,
                        client,
                        self.settings.libretranslate_url,
                        self.settings.libretranslate_api_key,
                    )
                except httpx.HTTPError as exc:
                    LOGGER.warning("Translation failed for %s: %s", article.url, exc)
                    continue
                if result is not None:
                    normalized = self._normalize_source(result.source)
                    if allow_unlisted or result.is_linkedin or normalized in trusted_sources:
                        translated.append(result)
        return translated

    @staticmethod
    def _normalize_source(value: str) -> str:
        cleaned = "".join(character for character in value.lower() if character.isalnum())
        return cleaned.removeprefix("the")

    def generate(self, now: datetime) -> Brief:
        start, end = self.coverage_window(now)
        raw = self.collect(start, end)
        prepared = prepare_articles(raw, end, self.interests)
        prepared = apply_feedback(prepared, self.db.feedback_rules())
        fresh = [article for article in prepared if not self.db.was_sent(article.fingerprint)]
        limit = int(self.interests.get("maximum_stories", 10))
        mix = self.interests.get("coverage_mix", {})
        selected = select_balanced(
            fresh,
            maximum=limit,
            mature_specialty_minimum=int(mix.get("mature_specialty_minimum", 5)),
            leading_edge_maximum=int(mix.get("leading_edge_maximum", 2)),
            packaging_addendum_maximum=int(mix.get("packaging_addendum_maximum", 3)),
            technology_addendum_maximum=int(mix.get("technology_addendum_maximum", 3)),
            regional_news_minimum=int(
                self.sources.get("regional_news", {}).get("minimum_stories", 3)
            ),
            regional_news_sources={
                str(name) for name in self.sources.get("regional_news", {}).get("sources", [])
            },
        )
        source_count = (
            len(self.sources.get("publishers", [])) + len(self.sources.get("direct_feeds", [])) + 1
        )
        return build_brief(selected, start, end, self.settings.timezone, source_count, len(raw))

    def run(self, now: datetime, dry_run: bool) -> Path:
        with run_lock(self.settings.database_path.with_suffix(".lock")):
            brief = self.generate(now)
            key_payload = f"{brief.window_start.isoformat()}|{brief.window_end.isoformat()}"
            key = hashlib.sha256(key_payload.encode()).hexdigest()
            if not dry_run and self.db.brief_exists(key):
                raise RuntimeError("This coverage window has already been processed")
            self.settings.output_dir.mkdir(parents=True, exist_ok=True)
            stem = f"semiconductor-brief-{now.astimezone(UTC):%Y-%m-%d}"
            text_path = self.settings.output_dir / f"{stem}.txt"
            html_path = self.settings.output_dir / f"{stem}.html"
            json_path = self.settings.output_dir / f"{stem}.json"
            text_path.write_text(brief.plain_text, encoding="utf-8")
            html_path.write_text(brief.html, encoding="utf-8")
            json_path.write_text(
                json.dumps(
                    {
                        "subject": brief.subject,
                        "window_start": brief.window_start.isoformat(),
                        "window_end": brief.window_end.isoformat(),
                        "stories": [
                            {
                                "title": item.title,
                                "url": item.url,
                                "source": item.source,
                                "impact": item.impact,
                                "tag": item.tag,
                                "score": item.score,
                            }
                            for item in brief.articles
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            sent_at = None
            if not dry_run:
                send_brief(brief)
                sent_at = now.astimezone(UTC)
                self.db.mark_success(sent_at)
                self.db.record_articles(brief.articles, sent_at)
            if not dry_run:
                self.db.record_brief(
                    key,
                    brief.subject,
                    brief.window_start,
                    brief.window_end,
                    text_path,
                    sent_at,
                )
            return text_path
