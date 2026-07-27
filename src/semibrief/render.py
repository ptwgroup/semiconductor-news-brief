from __future__ import annotations

import html
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from .editor import extractive_bullets, why_it_matters
from .models import Article, Brief


def _takeaways(articles: list[Article]) -> list[str]:
    if not articles:
        return ["No sufficiently material, verified developments were found in this window."]
    takeaways: list[str] = []
    for article in articles[:3]:
        takeaways.append(f"{article.tag}: {why_it_matters(article)}")
    while len(takeaways) < 3:
        takeaways.append("No additional high-confidence cross-industry signal was identified.")
    return takeaways


def build_brief(
    articles: list[Article],
    start: datetime,
    end: datetime,
    timezone: str,
    sources_monitored: int,
    articles_reviewed: int,
) -> Brief:
    zone = ZoneInfo(timezone)
    local_start = start.astimezone(zone)
    local_end = end.astimezone(zone)
    subject = f"Daily Semiconductor News Brief — {local_end:%Y-%m-%d}"
    lines = [
        subject,
        f"Coverage window: {local_start:%Y-%m-%d %H:%M} to {local_end:%Y-%m-%d %H:%M} SGT",
        "",
        "EXECUTIVE TAKEAWAYS",
    ]
    lines.extend(f"- {item}" for item in _takeaways(articles))
    lines.extend(["", "TOP DEVELOPMENTS"])

    top = [item for item in articles if not item.is_linkedin or item.linkedin_official]
    radar = [item for item in articles if item.is_linkedin and not item.linkedin_official]
    for article in top:
        lines.extend(["", f"[{article.impact}] [{article.tag}] {article.title}"])
        lines.extend(f"- {bullet}" for bullet in extractive_bullets(article))
        lines.append(f"- Why it matters: {why_it_matters(article)}")
        lines.append(f"- Source: {article.source} — {article.url}")
        for link in article.corroborating_urls[:2]:
            lines.append(f"- Corroborating source: {link}")
        if article.language.startswith("translated"):
            lines.append(f"- Translation: {article.language}")
    if radar:
        lines.extend(["", "RADAR"])
        for article in radar[:3]:
            lines.extend(
                [
                    f"- LinkedIn signal — not independently confirmed: {article.title}",
                    f"  {article.source} — {article.url}",
                ]
            )
    lines.extend(
        [
            "",
            f"Sources monitored: {sources_monitored} | "
            f"Articles reviewed: {articles_reviewed} | Stories selected: {len(articles)}",
        ]
    )
    plain = "\n".join(lines)
    html_body = _plain_to_html(plain)
    return Brief(
        subject=subject,
        plain_text=plain,
        html=html_body,
        articles=articles,
        window_start=start,
        window_end=end,
        sources_monitored=sources_monitored,
        articles_reviewed=articles_reviewed,
    )


def _plain_to_html(value: str) -> str:
    rows: list[str] = []
    url_pattern = re.compile(r"(https?://[^\s<]+)")
    for raw in value.splitlines():
        escaped = html.escape(raw)
        escaped = url_pattern.sub(r'<a href="\1">\1</a>', escaped)
        if raw.startswith("Daily Semiconductor"):
            rows.append(f"<h1>{escaped}</h1>")
        elif raw in {"EXECUTIVE TAKEAWAYS", "TOP DEVELOPMENTS", "RADAR"}:
            rows.append(f"<h2>{escaped.title()}</h2>")
        elif raw.startswith("- "):
            rows.append(f'<p style="margin:6px 0">&#8226; {escaped[2:]}</p>')
        elif raw.startswith("["):
            rows.append(f"<h3>{escaped}</h3>")
        elif raw:
            rows.append(f"<p>{escaped}</p>")
    return (
        '<!doctype html><html><body style="font-family:Arial,sans-serif;'
        'max-width:760px;margin:auto;line-height:1.45;color:#172033">'
        + "".join(rows)
        + "</body></html>"
    )
