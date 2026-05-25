"""Daglig djupanalys: välj bästa ämne från historiken och skriv en grävande artikel med Gemini Deep Research."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

from google import genai
from google.genai import types
from google.genai.errors import ClientError

import config
from storage import get_recent_published_posts

logger = logging.getLogger(__name__)

# Max väntetid för deep research (sekunder)
_POLL_INTERVAL = 10
_MAX_POLLS = 120  # 20 minuter


def _get_client() -> genai.Client:
    return genai.Client(api_key=config.GEMINI_API_KEY)


def _select_best_topic(posts: list[dict]) -> dict | None:
    """Använd Gemini för att välja det mest lovande ämnet från publiceringshistoriken."""
    if not posts:
        return None

    numbered = "\n".join(
        f"{i+1}. [{p['source']}] {p['title']} (score {p['score']}/10)\n"
        f"   Vinkel: {p['motivation']}"
        for i, p in enumerate(posts)
    )

    prompt = f"""Du är en politisk redaktör för Piratpartiet i Sverige.
Nedan listas de senaste nyheterna som partiet har kommenterat.
Välj det ämne som har störst potential för en djupgående, grävande artikel som kan
ge partiet genomslag i medierna och bidra till valkampanjen.

{numbered}

Svara med ett JSON-objekt:
{{
  "index": <nummer 1-{len(posts)}>,
  "reasoning": "<kort motivering på svenska, 1-2 meningar>"
}}
Svara BARA med JSON, inga andra tecken."""

    try:
        response = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
                max_output_tokens=300,
            ),
        )
        data = json.loads(response.text or "{}")
        idx = int(data.get("index", 1)) - 1
        idx = max(0, min(idx, len(posts) - 1))
        chosen = posts[idx]
        logger.info(
            "Valt ämne för deep research: '%s' (index %d). Skäl: %s",
            chosen["title"], idx + 1, data.get("reasoning", ""),
        )
        return chosen
    except Exception:
        logger.exception("Misslyckades att välja ämne – använder högst-poäng")
        return max(posts, key=lambda p: p["score"])


def _build_research_prompt(post: dict) -> str:
    return f"""Du är en undersökande journalist med djup kunskap om digitala rättigheter,
integritetsfrågor och teknikpolitik. Du skriver för Piratpartiet i Sverige.

Skriv en djupgående, grävande och välresearchad artikel på svenska baserad på följande nyhet:

**Nyhet:** {post['title']}
**Källa:** {post['source']}
**Partiets inledande vinkel:** {post['motivation']}

Artikeln ska:
- Vara 600-900 ord lång
- Gräva djupare än nyhetens yta – undersök bakgrund, kontext, aktörer och konsekvenser
- Lyfta fram perspektiv och fakta som är relevanta för Piratpartiets kärnfrågor (integritet, yttrandefrihet, upphovsrätt, digital demokrati)
- Använda konkreta fakta, siffror och hänvisningar till verkliga händelser eller dokument
- Ha en klar struktur med inledning, fördjupning och avslutande analys
- Vara skriven i en seriös men engagerande journalistisk ton
- Avsluta med en tydlig politisk poäng som Piratpartiet kan stå bakom

Använd Google Search för att hitta aktuella källor och fakta."""


def _extract_article_text(interaction) -> str:
    """Extrahera artikeltext från en avslutad interaction."""
    parts = []
    for step in (interaction.steps or []):
        if step.type == "model_output":
            for content in (step.content or []):
                if hasattr(content, "text") and content.text:
                    parts.append(content.text)
    return "\n\n".join(parts)


def run_deep_research() -> str | None:
    """Välj bästa ämne från historiken och generera en grävande artikel. Returnerar artikeltexten."""
    posts = get_recent_published_posts()
    if not posts:
        logger.info("Deep research: ingen historik att utgå från.")
        return None

    post = _select_best_topic(posts)
    if not post:
        return None

    logger.info("Startar deep research för: '%s'", post["title"])
    prompt = _build_research_prompt(post)

    try:
        client = _get_client()
        interaction = client.interactions.create(
            agent=config.DEEP_RESEARCH_AGENT,
            background=True,
            input=[{
                "type": "user_input",
                "content": [{"type": "text", "text": prompt}],
            }],
        )
        logger.info("Interaction skapad (id=%s), väntar på svar...", interaction.id)

        for poll in range(_MAX_POLLS):
            time.sleep(_POLL_INTERVAL)
            interaction = client.interactions.get(interaction.id)
            elapsed = (poll + 1) * _POLL_INTERVAL
            logger.debug("Deep research status: %s (%ds)", interaction.status, elapsed)
            if interaction.status == "completed":
                break
            if interaction.status in ("failed", "cancelled"):
                logger.error("Deep research avslutades med status: %s", interaction.status)
                return None
        else:
            logger.error("Deep research timeout efter %d sekunder.", _MAX_POLLS * _POLL_INTERVAL)
            return None

        article = _extract_article_text(interaction)
        if not article:
            logger.error("Deep research returnerade tom artikel.")
            return None

        logger.info("Deep research klar (%d tecken).", len(article))
        return article

    except Exception:
        logger.exception("Deep research misslyckades")
        return None


def _format_mattermost_article(article: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d")
    return (
        f"## 🔍 Piratpartiet Djupanalys – {timestamp}\n"
        f"*Genererad av NewsJacker Deep Research*\n\n"
        f"---\n\n"
        f"{article}\n\n"
        f"---\n"
        f"*Källa: AI-genererad analys baserad på aktuella nyheter och öppen information*"
    )


def run_daily_research_and_post() -> None:
    """Kör daglig deep research och posta till Mattermost."""
    logger.info("=== Startar daglig deep research ===")
    article = run_deep_research()
    if not article:
        logger.info("Ingen artikel genererades.")
        return

    from notifier import send_article
    send_article(_format_mattermost_article(article))
    logger.info("=== Daglig deep research klar ===")
