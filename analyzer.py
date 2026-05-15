"""Gemini-baserad relevansanalys och newsjacking-generator."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import TypedDict

from google import genai
from google.genai import types
from google.genai.errors import ClientError

import config

logger = logging.getLogger(__name__)

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
    wait = _BASE_WAIT
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = _get_client().models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                    max_output_tokens=1500,
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


def analyze_item(title: str, summary: str, url: str, source: str) -> AnalysisResult | None:
    """Analysera ett nyhetsitem och returnera relevanspoäng + newsjack-förslag."""
    user_prompt = f"""Källa: {source}
Rubrik: {title}
Sammanfattning: {summary}
URL: {url}

Analysera denna nyhet ur Piratpartiets perspektiv."""

    try:
        raw = _call_with_retry(f"{SYSTEM_PROMPT}\n\n{user_prompt}")
        data = json.loads(raw)

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


def analyze_batch(items: list[dict]) -> list[AnalysisResult]:
    """Analysera en lista nyheter och returnera resultat för alla."""
    results: list[AnalysisResult] = []
    for item in items:
        result = analyze_item(
            title=item.get("title", "") or item.get("text", ""),
            summary=item.get("summary", "") or item.get("text", ""),
            url=item["url"],
            source=item["source"],
        )
        if result is not None:
            logger.info("Score %d/10: %s", result["score"], result["title"][:60])
            results.append(result)
    return results
