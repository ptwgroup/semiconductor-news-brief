from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup

TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


def clean_text(value: str) -> str:
    text = BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    query = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        key: values
        for key, values in query.items()
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS
    }
    return urlunparse(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower().removeprefix("www."),
            parsed.path.rstrip("/") or "/",
            "",
            urlencode(filtered, doseq=True),
            "",
        )
    )


def normalize_headline(value: str) -> str:
    words = re.findall(r"[a-z0-9]+", value.lower())
    stop = {"a", "an", "and", "for", "in", "its", "of", "on", "the", "to", "with"}
    normalized = []
    for word in words:
        if word in stop:
            continue
        normalized.append(word[:-1] if word.endswith("s") and len(word) > 4 else word)
    return " ".join(normalized)


def fingerprint(title: str, url: str) -> str:
    payload = f"{normalize_headline(title)}|{canonicalize_url(url)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def headline_similarity(left: str, right: str) -> float:
    a = set(normalize_headline(left).split())
    b = set(normalize_headline(right).split())
    return len(a & b) / len(a | b) if a and b else 0.0


def parse_datetime(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    gdelt_match = re.fullmatch(r"(\d{8})T(\d{6})Z", value)
    if gdelt_match:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        from email.utils import parsedate_to_datetime

        parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def mask_email(value: str) -> str:
    local, separator, domain = value.partition("@")
    if not separator:
        return "***"
    return f"{local[:1]}***@{domain}"
