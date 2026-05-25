"""Gemini-baserad relevansanalys och newsjacking-generator."""
from __future__ import annotations

import json
import logging
import logging.handlers
import re
import time
from pathlib import Path
from typing import TypedDict

from google import genai
from google.genai import types
from google.genai.errors import ClientError

import config

logger = logging.getLogger(__name__)

# Dedikerad logger för alla promptar – roteras vid 100 KB, behåller 3 backup-filer
_prompt_logger = logging.getLogger("prompts")
_prompt_logger.setLevel(logging.DEBUG)
_prompt_logger.propagate = False  # hamnar inte i huvudloggen
_prompt_handler = logging.handlers.RotatingFileHandler(
    Path(__file__).parent / "prompts.log",
    maxBytes=100_000,
    backupCount=3,
    encoding="utf-8",
)
_prompt_handler.setFormatter(logging.Formatter("%(asctime)s\n%(message)s\n" + "=" * 80))
_prompt_logger.addHandler(_prompt_handler)

_client: genai.Client | None = None

# Throttling: max retries och bas-väntetid vid rate limit (sekunder)
_MAX_RETRIES = 5
_BASE_WAIT = 15  # sekunder – justeras upp om API:t anger längre väntetid


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _extract_retry_delay(exc: ClientError) -> float:
    """Extrahera retry_delay (sekunder) från felmeddelandet, returnerar 0 om ej hittad."""
    match = re.search(r"retry in (\d+(?:\.\d+)?)", str(exc), re.IGNORECASE)
    if match:
        return float(match.group(1))
    return 0.0


def _is_rate_limit(exc: ClientError) -> bool:
    return getattr(exc, "status_code", None) == 429 or "429" in str(exc)


def _call_with_retry(prompt: str) -> str:
    """Anropa Gemini med automatisk throttling vid 429-fel."""
    _prompt_logger.debug(prompt)
    wait = _BASE_WAIT
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = _get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                    max_output_tokens=3000,
                    thinking_config=types.ThinkingConfig(thinking_level="low"),
                ),
            )
            return response.text or "{}"

        except ClientError as exc:
            if not _is_rate_limit(exc):
                raise
            api_delay = _extract_retry_delay(exc)
            sleep_for = max(wait, api_delay + 2)
            logger.warning(
                "Rate limit (429) – försök %d/%d. Väntar %.0f s ...",
                attempt, _MAX_RETRIES, sleep_for,
            )
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(sleep_for)
            wait = min(wait * 2, 120)  # exponential backoff, tak 2 min

    return "{}"


class AnalysisResult(TypedDict):
    url: str
    title: str
    source: str
    score: int
    motivation: str
    newsjack_tweet: str
    newsjack_comment: str


SYSTEM_PROMPT = f"""Du är en politisk strateg för Piratpartiet i Sverige.
Din uppgift är att bedöma om en nyhet är relevant för partiets valkampanj och
i så fall föreslå hur partiet kan använda nyheten för "newsjacking".

{config.PARTY_CONTEXT}

Svara ALLTID med ett JSON-objekt (inga andra tecken utanför JSON):
{{
  "score": <heltal 0-10, där 10 = extremt relevant>,
  "motivation": "<kort motivering på svenska, 1-2 meningar>",
  "newsjack_tweet": "<tweet-utkast på svenska, max 240 tecken, inkl. relevanta hashtags>",
  "newsjack_comment": "<längre kommentar/pressmeddelande-inledning på svenska, 3-5 meningar>"
}}

Poängsättning:
- 0-2: Inte relevant för Piratpartiet
- 3-5: Svagt relevant, tangerar partiets frågor
- 6-7: Relevant, tydlig koppling till partiets frågor
- 8-9: Starkt relevant, direkt koppling till kärnfrågor
- 10: Perfekt newsjacking-möjlighet
"""


def _build_history_context(history: list[dict]) -> str:
    """Bygg en kompakt historiksektion för prompten."""
    if not history:
        return ""
    lines = ["\n\nSENASTE PUBLICERADE INLÄGG (undvik att upprepa samma vinkel/ton):"]
    for i, post in enumerate(history, 1):
        lines.append(
            f"{i}. [{post['source']}] {post['title']} (score {post['score']}/10)\n"
            f"   Vinkel: {post['motivation']}\n"
            f"   Tweet: {post['newsjack_tweet']}"
        )
    lines.append(
        "\nBaserat på ovanstående historik: välj en ny infallsvinkel, "
        "variera ton och formulering, och undvik att upprepa argument som redan använts."
    )
    return "\n".join(lines)


def analyze_item(title: str, summary: str, url: str, source: str,
                 history: list[dict] | None = None) -> AnalysisResult | None:
    """Analysera ett nyhetsitem och returnera relevanspoäng + newsjack-förslag."""
    history_context = _build_history_context(history or [])
    user_prompt = f"""Källa: {source}
Rubrik: {title}
Sammanfattning: {summary}
URL: {url}
{history_context}

Analysera denna nyhet ur Piratpartiets perspektiv."""

    try:
        raw = _call_with_retry(f"{SYSTEM_PROMPT}\n\n{user_prompt}")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error(
                "Ogiltigt JSON-svar för '%s' (trunkerat? %d tecken): %s…",
                title, len(raw), raw[:200],
            )
            return None

        return AnalysisResult(
            url=url,
            title=title,
            source=source,
            score=int(data.get("score", 0)),
            motivation=data.get("motivation", ""),
            newsjack_tweet=data.get("newsjack_tweet", ""),
            newsjack_comment=data.get("newsjack_comment", ""),
        )
    except Exception:
        logger.exception("Analys misslyckades för '%s'", title)
        return None


def analyze_batch(items: list[dict], history: list[dict] | None = None) -> list[AnalysisResult]:
    """Analysera en lista nyheter och returnera resultat för alla."""
    results: list[AnalysisResult] = []
    for item in items:
        result = analyze_item(
            title=item.get("title", "") or item.get("text", ""),
            summary=item.get("summary", "") or item.get("text", ""),
            url=item["url"],
            source=item["source"],
            history=history,
        )
        if result is not None:
            logger.info("Score %d/10: %s", result["score"], result["title"][:60])
            results.append(result)
    return results
