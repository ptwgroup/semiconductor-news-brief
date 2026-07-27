from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Any

import httpx

from .models import Article
from .util import clean_text, fingerprint, headline_similarity

TOPIC_RULES: dict[str, tuple[str, ...]] = {
    "Mature Nodes": (
        "mature node",
        "legacy node",
        "essential chip",
        "40nm",
        "45nm",
        "48nm",
        "55nm",
        "65nm",
        "90nm",
        "110nm",
        "130nm",
        "180nm",
        "200mm",
    ),
    "MEMS & Sensors": (
        "mems",
        "microelectromechanical",
        "accelerometer",
        "gyroscope",
        "pressure sensor",
        "image sensor",
        "mems microphone",
        "timing device",
    ),
    "Power Devices": (
        "power semiconductor",
        "silicon carbide",
        "sic",
        "gallium nitride",
        "gan",
        "igbt",
        "mosfet",
        "superjunction",
        "power management",
        "pmic",
        "high voltage",
    ),
    "Analog/Mixed-Signal": (
        "analog",
        "mixed-signal",
        "mixed signal",
        "specialty cmos",
        "bcd",
        "rf cmos",
        "sige",
        "microcontroller",
        "mcu",
        "embedded non-volatile",
        "eeprom",
    ),
    "Photonics/RF": (
        "photonics",
        "optoelectronics",
        "rf semiconductor",
        "radio frequency",
        "gaas",
        "indium phosphide",
        "inp",
    ),
    "Policy/Trade": ("export control", "sanction", "tariff", "chips act", "subsid"),
    "Foundry": ("foundry", "fab", "process node", "nanometer", "wafer"),
    "Memory": ("dram", "nand", "hbm", "memory"),
    "Equipment": ("lithography", "euv", "equipment", "asml", "applied materials", "kla"),
    "Materials": ("silicon wafer", "photoresist", "chemical", "substrate", "gas"),
    "Packaging": ("packaging", "chiplet", "osat", "hybrid bonding"),
    "AI Chips": ("accelerator", "gpu", "ai chip", "data center", "nvidia"),
    "Automotive": ("automotive", "vehicle", "car chip"),
    "Earnings": ("earnings", "revenue", "forecast", "guidance", "profit"),
    "M&A": ("acquisition", "merger", "takeover", "buyout"),
}

CLASSIFICATION_ORDER = (
    "MEMS & Sensors",
    "Power Devices",
    "Mature Nodes",
    "Analog/Mixed-Signal",
    "Photonics/RF",
    "Policy/Trade",
    "Automotive",
    "Materials",
    "Packaging",
    "Equipment",
    "Memory",
    "AI Chips",
    "Foundry",
    "Earnings",
    "M&A",
)

IMPACT_TERMS = {
    "shutdown": 3.0,
    "earthquake": 3.0,
    "export control": 2.5,
    "sanction": 2.5,
    "billion": 2.0,
    "acquisition": 2.0,
    "mass production": 2.0,
    "fab": 1.5,
    "capacity": 1.5,
    "investment": 1.5,
    "shortage": 1.5,
    "hbm": 1.5,
    "euv": 1.5,
    "mature node": 2.0,
    "specialty cmos": 2.0,
    "mems": 2.0,
    "power semiconductor": 2.0,
    "silicon carbide": 1.8,
    "gallium nitride": 1.8,
    "analog": 1.5,
    "mixed-signal": 1.5,
    "200mm": 1.5,
    "semiconductor": 1.0,
    "chip": 0.8,
}

LOW_VALUE_TERMS = {
    "better investment": 10.0,
    "price target": 8.0,
    "stock to buy": 8.0,
    "stake in": 6.0,
    "etf": 5.0,
    "technical analysis": 8.0,
    "consumer review": 8.0,
}


def translate_if_needed(
    article: Article,
    client: httpx.Client,
    endpoint: str | None,
    api_key: str | None,
) -> Article | None:
    language = article.language.lower()
    if language in {"en", "eng", "english", ""}:
        return article
    if not endpoint:
        return None
    response = client.post(
        f"{endpoint.rstrip('/')}/translate",
        json={
            "q": f"{article.title}\n{article.summary}",
            "source": "auto",
            "target": "en",
            "format": "text",
            "api_key": api_key or "",
        },
    )
    response.raise_for_status()
    translated = str(response.json()["translatedText"])
    title, _, summary = translated.partition("\n")
    article.title = clean_text(title)
    article.summary = clean_text(summary)
    article.language = f"translated from {language}"
    return article


def classify(article: Article) -> str:
    title = article.title.lower()
    for tag in CLASSIFICATION_ORDER:
        terms = TOPIC_RULES[tag]
        if any(term in title for term in terms):
            return tag
    haystack = f"{article.title} {article.summary}".lower()
    for tag in CLASSIFICATION_ORDER:
        terms = TOPIC_RULES[tag]
        if any(term in haystack for term in terms):
            return tag
    return "Supply Chain"


def score_article(
    article: Article,
    now: datetime,
    interests: dict[str, Any],
) -> float:
    haystack = f"{article.title} {article.summary}".lower()
    score = float(article.source_priority) * 1.2
    score += sum(weight for term, weight in IMPACT_TERMS.items() if term in haystack)
    score -= sum(weight for term, weight in LOW_VALUE_TERMS.items() if term in haystack)
    companies = [str(item).lower() for item in interests.get("priority_companies", [])]
    topics = [str(item).lower() for item in interests.get("priority_topics", [])]
    regions = [str(item).lower() for item in interests.get("priority_regions", [])]
    score += min(3.0, sum(0.8 for company in companies if company in haystack))
    score += min(2.0, sum(0.6 for topic in topics if topic in haystack))
    if article.region.lower() in regions:
        score += 0.7
    excluded = [str(item).lower() for item in interests.get("excluded_topics", [])]
    if any(term in haystack for term in excluded):
        score -= 20
    age_hours = max(0.0, (now - article.published_at).total_seconds() / 3600)
    score += max(0.0, 2.0 - age_hours / 24)
    if article.is_linkedin and not article.linkedin_official:
        score -= 2.0
    return round(score, 2)


def deduplicate(articles: list[Article]) -> list[Article]:
    selected: list[Article] = []
    seen_urls: set[str] = set()
    for article in sorted(articles, key=lambda item: item.score, reverse=True):
        if article.url in seen_urls:
            continue
        duplicate = next(
            (
                existing
                for existing in selected
                if headline_similarity(article.title, existing.title) >= 0.62
            ),
            None,
        )
        if duplicate:
            if article.url != duplicate.url:
                duplicate.corroborating_urls.append(article.url)
            continue
        selected.append(article)
        seen_urls.add(article.url)
    return selected


def prepare_articles(
    articles: list[Article],
    now: datetime,
    interests: dict[str, Any],
) -> list[Article]:
    for article in articles:
        article.fingerprint = fingerprint(article.title, article.url)
        article.tag = classify(article)
        article.score = score_article(article, now, interests)
        article.impact = (
            "CRITICAL" if article.score >= 13 else "HIGH" if article.score >= 9 else "WATCH"
        )
    return deduplicate([article for article in articles if article.score >= 5])


def apply_feedback(articles: list[Article], rules: list[tuple[str, str]]) -> list[Article]:
    adjustments = {
        "more_like_this": 1.5,
        "less_like_this": -1.5,
        "irrelevant": -4.0,
    }
    for article in articles:
        for prior_title, preference in rules:
            if headline_similarity(article.title, prior_title) >= 0.3:
                article.score += adjustments.get(preference, 0.0)
        article.score = round(article.score, 2)
        article.impact = (
            "CRITICAL" if article.score >= 13 else "HIGH" if article.score >= 9 else "WATCH"
        )
    return sorted(articles, key=lambda item: item.score, reverse=True)


SPECIALTY_TAGS = {
    "Mature Nodes",
    "MEMS & Sensors",
    "Power Devices",
    "Analog/Mixed-Signal",
    "Photonics/RF",
    "Automotive",
    "Materials",
}

LEADING_EDGE_TERMS = {
    "1.4nm",
    "1.6nm",
    "2nm",
    "3nm",
    "high-na euv",
    "hbm",
    "ai accelerator",
    "gpu",
}


def select_balanced(
    articles: list[Article],
    maximum: int,
    mature_specialty_minimum: int,
    leading_edge_maximum: int,
) -> list[Article]:
    ranked = sorted(articles, key=lambda item: item.score, reverse=True)
    specialty = [item for item in ranked if item.tag in SPECIALTY_TAGS]
    selected = specialty[: min(maximum, mature_specialty_minimum)]
    selected_ids = {item.fingerprint for item in selected}
    leading_count = 0

    for article in ranked:
        if len(selected) >= maximum:
            break
        if article.fingerprint in selected_ids:
            continue
        haystack = f"{article.title} {article.summary}".lower()
        is_leading = any(term in haystack for term in LEADING_EDGE_TERMS)
        if is_leading and leading_count >= leading_edge_maximum:
            continue
        selected.append(article)
        selected_ids.add(article.fingerprint)
        if is_leading:
            leading_count += 1

    if len(selected) < maximum:
        for article in ranked:
            if len(selected) >= maximum:
                break
            if article.fingerprint not in selected_ids:
                selected.append(article)
                selected_ids.add(article.fingerprint)
    return selected


def extractive_bullets(article: Article, limit: int = 2) -> list[str]:
    text = clean_text(article.summary)
    sentences = [
        item.strip() for item in re.split(r"(?<=[.!?])\s+", text) if 35 <= len(item.strip()) <= 280
    ]
    if not sentences:
        return [article.title.rstrip(".") + "."]
    title_words = set(re.findall(r"[a-z0-9]+", article.title.lower()))
    common = Counter(re.findall(r"[a-z0-9]+", text.lower()))
    ranked = sorted(
        enumerate(sentences),
        key=lambda pair: (
            sum(common[word] for word in set(re.findall(r"[a-z0-9]+", pair[1].lower()))),
            len(title_words & set(re.findall(r"[a-z0-9]+", pair[1].lower()))),
        ),
        reverse=True,
    )
    chosen_indexes = sorted(index for index, _ in ranked[:limit])
    return [sentences[index] for index in chosen_indexes]


def why_it_matters(article: Article) -> str:
    messages = {
        "Policy/Trade": "May change market access, sourcing choices, or compliance costs.",
        "Foundry": "Could alter available manufacturing capacity, lead times, or node economics.",
        "Memory": "May affect memory availability, pricing, and AI-system build costs.",
        "Equipment": "Could influence fab expansion timing and leading-edge production capability.",
        "Materials": "May affect upstream availability, qualification timelines, and wafer costs.",
        "Mature Nodes": (
            "May affect long-lifecycle capacity, utilization, pricing, and second-source options."
        ),
        "MEMS & Sensors": (
            "May affect sensor availability, qualification cycles, packaging, "
            "and application demand."
        ),
        "Power Devices": (
            "May affect automotive, industrial, energy, and data-center "
            "power-system cost or supply."
        ),
        "Analog/Mixed-Signal": (
            "May affect control, interface, power-management, and long-lifecycle product supply."
        ),
        "Photonics/RF": (
            "May affect optical connectivity, communications, sensing, "
            "and specialist material demand."
        ),
        "Packaging": "Could change advanced-packaging capacity and accelerator supply.",
        "AI Chips": (
            "May shift accelerator supply, performance competition, or data-center spending."
        ),
        "Automotive": "Could affect long-lifecycle component supply and vehicle production.",
        "Earnings": (
            "Provides a current signal on demand, inventory, pricing, and capital spending."
        ),
        "M&A": (
            "Could reshape technology ownership, supplier concentration, or regulatory scrutiny."
        ),
        "Supply Chain": "May affect semiconductor supply, demand visibility, or execution risk.",
    }
    return messages[article.tag]
