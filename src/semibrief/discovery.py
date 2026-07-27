from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urlparse

import feedparser  # type: ignore[import-untyped]
import httpx

from .models import Article
from .util import canonicalize_url, clean_text, parse_datetime

LOGGER = logging.getLogger(__name__)


def _publisher_for(url: str, publishers: list[dict[str, Any]]) -> tuple[str, str, int]:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for publisher in publishers:
        domain = str(publisher["domain"]).lower()
        if host == domain or host.endswith(f".{domain}"):
            return (
                str(publisher["name"]),
                str(publisher.get("region", "Global")),
                int(publisher.get("priority", 3)),
            )
    return host or "Unknown", "Global", 2


def fetch_feed(
    client: httpx.Client,
    url: str,
    source: str,
    region: str,
    priority: int,
) -> list[Article]:
    response = client.get(url)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    articles: list[Article] = []
    for entry in parsed.entries:
        link = str(entry.get("link", "")).strip()
        title = clean_text(str(entry.get("title", "")))
        if not link or not title:
            continue
        published = entry.get("published") or entry.get("updated")
        entry_source = entry.get("source", {})
        detected_source = (
            clean_text(str(entry_source.get("title", ""))) if isinstance(entry_source, dict) else ""
        )
        final_source = detected_source or source
        suffix = f" - {final_source}"
        if detected_source and title.endswith(suffix):
            title = title[: -len(suffix)].strip()
        articles.append(
            Article(
                title=title,
                url=canonicalize_url(link),
                source=final_source,
                summary=clean_text(str(entry.get("summary", "") or entry.get("description", ""))),
                published_at=parse_datetime(str(published) if published else None),
                region=region,
                source_priority=priority,
            )
        )
    return articles


def fetch_gdelt(
    client: httpx.Client,
    settings: dict[str, Any],
    publishers: list[dict[str, Any]],
    timespan_hours: int,
) -> list[Article]:
    params: dict[str, str | int] = {
        "query": str(settings["query"]).replace("\n", " "),
        "mode": "artlist",
        "maxrecords": min(int(settings.get("max_records", 250)), 250),
        "timespan": f"{max(1, min(timespan_hours, 168))}h",
        "sort": "datedesc",
        "format": "json",
    }
    payload: dict[str, Any] | None = None
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = client.get(str(settings["endpoint"]), params=params)
            response.raise_for_status()
            if not response.content:
                raise ValueError("GDELT returned an empty response")
            decoded = response.json()
            if not isinstance(decoded, dict):
                raise ValueError("GDELT returned non-object JSON")
            payload = decoded
            break
        except (httpx.HTTPError, ValueError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(6 * (attempt + 1))
    if payload is None:
        raise ValueError(f"GDELT failed after retries: {last_error}")
    results: list[Article] = []
    for item in payload.get("articles", []):
        url = canonicalize_url(str(item.get("url", "")))
        title = clean_text(str(item.get("title", "")))
        if not url or not title:
            continue
        source, region, priority = _publisher_for(url, publishers)
        results.append(
            Article(
                title=title,
                url=url,
                source=source,
                summary=clean_text(str(item.get("seendate", ""))),
                published_at=parse_datetime(str(item.get("seendate", ""))),
                language=str(item.get("language", "English")).lower(),
                region=region,
                source_priority=priority,
            )
        )
    return results


def google_news_url(query: str, language: str, country: str) -> str:
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={language}-{country}&gl={country}&ceid={country}:{language}"
    )


def fetch_linkedin_urls(client: httpx.Client, path: Path, now: datetime) -> list[Article]:
    import yaml
    from bs4 import BeautifulSoup

    if not path.exists():
        return []
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    results: list[Article] = []
    for record in payload.get("posts", []):
        url = str(record.get("url", ""))
        if "linkedin.com/" not in url:
            LOGGER.warning("Skipping non-LinkedIn URL in %s", path)
            continue
        try:
            response = client.get(url)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            LOGGER.info("LinkedIn URL unavailable; skipped: %s", exc)
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        title_meta = soup.select_one('meta[property="og:title"]')
        description_meta = soup.select_one('meta[property="og:description"]')
        title = clean_text(str(title_meta.get("content", "")) if title_meta else "")
        summary = clean_text(str(description_meta.get("content", "")) if description_meta else "")
        if not title:
            continue
        results.append(
            Article(
                title=title,
                url=canonicalize_url(url),
                source=f"LinkedIn — {record.get('account', 'configured account')}",
                summary=summary,
                published_at=now.astimezone(UTC),
                region=str(record.get("region", "Global")),
                source_priority=4 if record.get("official", False) else 2,
                is_linkedin=True,
                linkedin_official=bool(record.get("official", False)),
            )
        )
    return results
