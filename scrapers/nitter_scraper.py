"""Nitter scraper – hämtar tweets via Nitter (öppen Twitter-frontend).

Stödjer automatisk fallback mellan flera Nitter-instanser om
primär-instansen inte svarar eller returnerar tomt innehåll.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import TypedDict

import httpx
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
}

TIMEOUT = 20.0


class Tweet(TypedDict):
    text: str
    url: str
    author: str
    timestamp: datetime
    source: str


def _search_url(nitter_instance: str, query: str) -> str:
    encoded = query.replace("#", "%23").replace(" ", "+")
    return f"{nitter_instance.rstrip('/')}/search?f=tweets&q={encoded}"


def _parse_tweets(html: str, instance: str, term: str) -> list[Tweet]:
    """Parsa tweet-objekt ur Nitter-HTML."""
    soup = BeautifulSoup(html, "html.parser")
    tweets: list[Tweet] = []

    for item in soup.select(".timeline-item"):
        text_el = item.select_one(".tweet-content")
        link_el = item.select_one("a.tweet-link")
        author_el = item.select_one(".username")
        time_el = item.select_one(".tweet-date a")

        if not text_el or not link_el:
            continue

        text = text_el.get_text(separator=" ").strip()
        tweet_path = link_el.get("href", "")
        tweet_url = (
            f"https://twitter.com{tweet_path}"
            if tweet_path.startswith("/")
            else tweet_path
        )
        author = (author_el.get_text().strip() if author_el else "okänd").lstrip("@")
        timestamp = _parse_nitter_time(time_el)

        tweets.append(
            Tweet(
                text=text,
                url=tweet_url,
                author=author,
                timestamp=timestamp,
                source=f"Twitter ({term})",
            )
        )
    return tweets


def _try_fetch(instance: str, term: str) -> list[Tweet]:
    """Försök hämta tweets från en specifik Nitter-instans."""
    url = _search_url(instance, term)
    with httpx.Client(headers=HEADERS, timeout=TIMEOUT, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()

    if len(response.text) < 200:
        raise ValueError(f"Tom respons från {instance}")

    tweets = _parse_tweets(response.text, instance, term)
    return tweets


def fetch_term(term: str) -> list[Tweet]:
    """Hämta tweets för en sökning. Provar primär instans sedan fallbacks."""
    instances = [config.NITTER_INSTANCE] + config.NITTER_FALLBACKS

    for instance in instances:
        try:
            tweets = _try_fetch(instance, term)
            if tweets:
                logger.info("Nitter '%s' via %s: %d tweets", term, instance, len(tweets))
                return tweets
            logger.debug("Nitter '%s' via %s: inga tweets", term, instance)
        except httpx.HTTPStatusError as exc:
            logger.warning("Nitter HTTP-fel %s för '%s': %s", instance, term, exc.response.status_code)
        except Exception as exc:
            logger.warning("Nitter-fel %s för '%s': %s", instance, term, exc)

    logger.warning("Alla Nitter-instanser misslyckades för '%s'", term)
    return []


def fetch_all(search_terms: list[str]) -> list[Tweet]:
    """Hämta tweets för alla söktermer."""
    all_tweets: list[Tweet] = []
    for term in search_terms:
        all_tweets.extend(fetch_term(term))
    return all_tweets


def _parse_nitter_time(time_el) -> datetime:
    """Parsa tidsstämpel från Nitters title-attribut."""
    if not time_el:
        return datetime.now(tz=timezone.utc)
    title = time_el.get("title", "")
    try:
        clean = re.sub(r"\s*·\s*", " ", title).replace(" UTC", "")
        return datetime.strptime(clean, "%b %d, %Y %H:%M").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    return datetime.now(tz=timezone.utc)
