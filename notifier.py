"""Notifieringar via Mattermost incoming webhook."""
from __future__ import annotations

import logging
import json
from datetime import datetime
from pathlib import Path

import httpx

import config
from analyzer import AnalysisResult

logger = logging.getLogger(__name__)


def _score_emoji(score: int) -> str:
    if score >= 9:
        return "🔴"
    if score >= 7:
        return "🟠"
    return "🟡"


def _build_message(results: list[AnalysisResult]) -> str:
    """Bygg Mattermost-meddelande i Markdown."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"## 🏴‍☠️ NewsJacker – {len(results)} newsjacking-möjligheter [{timestamp}]",
        "---",
    ]
    for r in sorted(results, key=lambda x: x["score"], reverse=True):
        emoji = _score_emoji(r["score"])
        lines += [
            f"### {emoji} {r['score']}/10 – [{r['title']}]({r['url']})",
            f"*Källa: {r['source']}*",
            f"> {r['motivation']}",
            "",
            f"**🐦 Tweet-förslag:**",
            f"```",
            r["newsjack_tweet"],
            f"```",
            f"**📝 Kommentar:**",
            r["newsjack_comment"],
            "---",
        ]
    return "\n".join(lines)


def _write_log(message: str) -> None:
    """Skriv meddelandet till mail_log.html för felsökning."""
    log_path = Path(__file__).parent / "mail_log.html"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(
            f"<!-- Mattermost-meddelande loggat {timestamp} -->\n"
            f"<pre style='font-family:monospace;white-space:pre-wrap;padding:20px'>"
            f"{message}</pre>"
        )
    logger.info("Meddelande sparat i %s", log_path)


def resend_from_log() -> None:
    """Läs senaste meddelandet från mail_log.html och skicka till Mattermost igen."""
    log_path = Path(__file__).parent / "mail_log.html"
    if not log_path.exists():
        logger.error("Ingen mail_log.html hittades – inget att skicka.")
        return

    content = log_path.read_text(encoding="utf-8")

    # Extrahera Markdown-texten mellan <pre ...> och </pre>
    start = content.find(">", content.find("<pre")) + 1
    end = content.rfind("</pre>")
    if start <= 0 or end <= 0:
        logger.error("Kunde inte tolka mail_log.html – oväntat format.")
        return

    message = content[start:end]
    logger.info("Skickar om senaste loggade meddelandet till Mattermost…")

    try:
        response = httpx.post(
            config.MATTERMOST_WEBHOOK_URL,
            content=json.dumps({"text": message}),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        logger.info("Meddelande skickat om.")
    except Exception:
        logger.exception("Misslyckades att skicka till Mattermost")


def send_digest(results: list[AnalysisResult]) -> None:
    """Skicka digest till Mattermost via incoming webhook."""
    if not results:
        logger.info("Inga relevanta nyheter att skicka.")
        return

    message = _build_message(results)
    _write_log(message)

    try:
        response = httpx.post(
            config.MATTERMOST_WEBHOOK_URL,
            content=json.dumps({"text": message}),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        response.raise_for_status()
        logger.info("Mattermost-notis skickad (%d nyheter)", len(results))
    except Exception:
        logger.exception("Misslyckades att skicka till Mattermost")
