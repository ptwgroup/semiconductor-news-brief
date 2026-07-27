from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Article:
    title: str
    url: str
    source: str
    published_at: datetime
    summary: str = ""
    language: str = "en"
    region: str = "Global"
    source_priority: int = 3
    is_linkedin: bool = False
    linkedin_official: bool = False
    score: float = 0.0
    tag: str = "Supply Chain"
    impact: str = "WATCH"
    fingerprint: str = ""
    corroborating_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Brief:
    subject: str
    plain_text: str
    html: str
    articles: list[Article]
    window_start: datetime
    window_end: datetime
    sources_monitored: int
    articles_reviewed: int
