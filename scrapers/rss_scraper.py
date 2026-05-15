"""RSS scraper – hämtar artiklar från svenska nyhetssajter."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TypedDict

import feedparser

logger = logging.getLogger(__name__)


class Article(TypedDict):
    title: str
    url: str
    summary: str
    published: datetime
    source: str


def fetch_feed(feed: dict) -> list[Article]:
    """Hämta och parsa en enskild RSS-feed."""
    name = feed["name"]
    url = feed["url"]
    articles: list[Article] = []

    try:
        parsed = feedparser.parse(url)
        if parsed.bozo and parsed.bozo_exception:
            logger.warning("Feed %s returnerade varning: %s", name, parsed.bozo_exception)

        for entry in parsed.entries:
            link = entry.get("link") or entry.get("id", "")
            if not link:
                continue

            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            # Rensa bort HTML-taggar ur summary
            summary = _strip_html(summary)[:500]

            published = _parse_date(entry)

            articles.append(
                Article(
                    title=title,
                    url=link,
                    summary=summary,
                    published=published,
                    source=name,
                )
            )
    except Exception:
        logger.exception("Misslyckades att hämta feed %s (%s)", name, url)

    logger.info("Feed '%s': %d artiklar hämtade", name, len(articles))
    return articles


def fetch_all(feeds: list[dict]) -> list[Article]:
    """Hämta artiklar från alla RSS-feeds."""
    all_articles: list[Article] = []
    for feed in feeds:
        all_articles.extend(fetch_feed(feed))
    return all_articles


def _parse_date(entry) -> datetime:
    """Försök extrahera publiceringsdatum, fallback till nu."""
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return datetime.now(tz=timezone.utc)


def _strip_html(text: str) -> str:
    """Enkel HTML-strippning utan externa beroenden."""
    import re
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
