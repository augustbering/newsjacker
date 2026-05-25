"""NewsJacker – huvudentrypoint med schemaläggning."""
from __future__ import annotations

import logging
import sys
import time
import argparse

import schedule

import config
import storage
from analyzer import analyze_item
from keyword_filter import filter_items
from dedup import deduplicate_items
from notifier import send_result, resend_from_log
from storage import get_recent_published_posts
from deep_researcher import run_daily_research_and_post
from scrapers import nitter_scraper, rss_scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("newsjacker.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("newsjacker")


def run_cycle() -> None:
    """En komplett insamlings- och analyscykel."""
    logger.info("=== Startar ny NewsJacker-cykel ===")

    # 1. Hämta nyheter
    articles = rss_scraper.fetch_all(config.RSS_FEEDS)
    tweets = []#nitter_scraper.fetch_all(config.NITTER_SEARCH_TERMS)
    logger.info("Hämtade %d artiklar och %d tweets", len(articles), len(tweets))

    # 2. Filtrera bort redan sedda
    new_articles = [a for a in articles if not storage.is_seen(a["url"])]
    new_tweets = [t for t in tweets if not storage.is_seen(t["url"])]
    logger.info(
        "Nya (ej sedda): %d artiklar, %d tweets",
        len(new_articles),
        len(new_tweets),
    )

    if not new_articles and not new_tweets:
        logger.info("Inget nytt att analysera.")
        return

    # 3. Slå ihop till ett gemensamt format för filter + analyzer
    items: list[dict] = []
    for a in new_articles:
        items.append({
            "title": a["title"],
            "summary": a["summary"],
            "url": a["url"],
            "source": a["source"],
        })
    for t in new_tweets:
        items.append({
            "title": t["text"][:100],
            "summary": t["text"],
            "url": t["url"],
            "source": t["source"],
        })

    # 4. Filtrera bort titelduplikat (samma nyhet från flera källor)
    items, dup_items = deduplicate_items(items)
    storage.mark_seen_batch([i["url"] for i in dup_items])

    # 5. Nyckelordsfilter – grovgallring för att spara API-kvot
    useFilter = config.KEYWORD_FILTER_ENABLED
    if useFilter:
        candidates, dropped = filter_items(items)
        logger.info(
            "Nyckelordsfilter: %d vidare till AI, %d bortfiltrerade",
            len(candidates), len(dropped),
        )

        # Markera bortfiltrerade som sedda så de inte återkommer
        storage.mark_seen_batch([i["url"] for i in dropped])
    else:
        candidates = items
        logger.info("Nyckelordsfilter inaktiverat – alla %d items går vidare", len(candidates)) 
    if not candidates:
        storage.mark_seen_batch([i["url"] for i in items])
        logger.info("Inga kandidater efter nyckelordsfilter.")
        return

    # 6. Analysera med Gemini och skicka direkt vid träff
    history = get_recent_published_posts()
    if history:
        logger.info("Skickar %d publicerade inlägg som historikkontext till Gemini", len(history))

    sent = 0
    for item in candidates:
        result = analyze_item(
            title=item.get("title", "") or item.get("text", ""),
            summary=item.get("summary", "") or item.get("text", ""),
            url=item["url"],
            source=item["source"],
            history=history,
        )
        storage.mark_seen(item["url"])
        if result is None:
            continue
        logger.info("Score %d/10: %s", result["score"], result["title"][:60])
        if result["score"] >= config.RELEVANCE_THRESHOLD:
            if send_result(result):
                sent += 1

    logger.info("=== Cykel klar – %d nyheter skickade ===", sent)


def main() -> None:
    parser = argparse.ArgumentParser(description="NewsJacker – nyhetsbevakningsagent")
    parser.add_argument(
        "--resend",
        action="store_true",
        help="Skicka om senaste resultaten från mail_log.html utan att söka nya nyheter.",
    )
    parser.add_argument(
        "--deep-research",
        action="store_true",
        help="Kör deep research direkt och posta till Mattermost.",
    )

    args = parser.parse_args()
    storage.init_db()

    if args.resend:
        resend_from_log()
        return

    if args.deep_research:
        run_daily_research_and_post()
        return

    logger.info(
        "NewsJacker startar – kör var %d:e timme (tröskel: %d/10)",
        config.SCHEDULE_HOURS,
        config.RELEVANCE_THRESHOLD,
    )

    # Kör direkt vid start
    run_cycle()

    # Schemalägg regelbundna körningar
    schedule.every(config.SCHEDULE_HOURS).hours.do(run_cycle)
    logger.info("Nästa körning om %d timmar.", config.SCHEDULE_HOURS)

    # Daglig deep research – kör kl 08:00
    schedule.every().day.at("08:00").do(run_daily_research_and_post)
    logger.info("Daglig deep research schemalagd kl 08:00.")

    while True:
        schedule.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
