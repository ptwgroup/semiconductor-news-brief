import json
from pathlib import Path

import httpx

from semibrief.discovery import fetch_feed, fetch_gdelt, google_news_url

FIXTURES = Path(__file__).parent / "fixtures"


def client_for(body: bytes, content_type: str) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": content_type})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_feed() -> None:
    body = (FIXTURES / "feed.xml").read_bytes()
    with client_for(body, "application/rss+xml") as client:
        articles = fetch_feed(client, "https://feed.test", "Test", "Taiwan", 5)
    assert len(articles) == 2
    assert articles[0].url == "https://example.com/tsmc-packaging"
    assert articles[0].region == "Taiwan"


def test_fetch_gdelt_maps_publisher() -> None:
    body = json.dumps(json.loads((FIXTURES / "gdelt.json").read_text())).encode()
    publishers = [{"name": "Reuters", "domain": "reuters.com", "region": "Global", "priority": 5}]
    settings = {
        "endpoint": "https://gdelt.test",
        "query": "semiconductor",
        "max_records": 10,
    }
    with client_for(body, "application/json") as client:
        articles = fetch_gdelt(client, settings, publishers, 24)
    assert articles[0].source == "Reuters"
    assert articles[0].source_priority == 5


def test_google_news_url_encodes_query() -> None:
    url = google_news_url("chip export controls", "en", "SG")
    assert "chip+export+controls" in url
    assert "ceid=SG:en" in url
