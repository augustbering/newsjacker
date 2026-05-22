"""Notifieringar via Mattermost incoming webhook."""
from __future__ import annotations

import re
import logging
import json
from datetime import datetime
from pathlib import Path

import httpx

import config
from analyzer import AnalysisResult
from storage import save_published_post

logger = logging.getLogger(__name__)


def _score_emoji(score: int) -> str:
    if score >= 9:
        return "🔴"
    if score >= 7:
        return "🟠"
    return "🟡"


def _strip_markdown_headings(text: str) -> str:
    """Ta bort markdown-rubriksyntax (#, ##, ###) så texten renderas som brödtext."""
    return re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)


def _build_item_message(r: AnalysisResult) -> str:
    """Bygg ett Mattermost-meddelande för ett enskilt nyhetsitem."""
    emoji = _score_emoji(r["score"])
    lines = [
        f"### {emoji} {r['score']}/10 – [{r['title']}]({r['url']})",
        f"*Källa: {r['source']}*",
        f"> {r['motivation']}",
        "",
        "**🐦 Tweet-förslag:**",
        "```",
        r["newsjack_tweet"],
        "```",
        "**📝 Kommentar:**",
        _strip_markdown_headings(r["newsjack_comment"]),
    ]
    return "\n".join(lines)


def _post_to_mattermost(message: str) -> None:
    response = httpx.post(
        config.MATTERMOST_WEBHOOK_URL,
        content=json.dumps({"text": message}),
        headers={"Content-Type": "application/json"},
        timeout=15,
    )
    response.raise_for_status()


def _write_log(message: str) -> None:
    """Append ett meddelande till mail_log.html för felsökning."""
    log_path = Path(__file__).parent / "mail_log.html"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    separator = "=" * 80
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"\n<!-- {timestamp} -->\n<pre style='font-family:monospace;white-space:pre-wrap;padding:20px'>{message}\n{separator}</pre>\n")


def send_result(r: AnalysisResult) -> bool:
    """Skicka ett enskilt analysresultat till Mattermost. Returnerar True vid lyckat anrop."""
    message = _build_item_message(r)
    _write_log(message)
    try:
        _post_to_mattermost(message)
        save_published_post(r)
        logger.info("Skickade: %s (%d/10)", r["title"][:60], r["score"])
        return True
    except Exception:
        logger.exception("Misslyckades att skicka '%s'", r["title"][:60])
        return False


def resend_from_log() -> None:
    """Läs senaste meddelanden från mail_log.html och skicka till Mattermost igen."""
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

    combined = content[start:end]
    separator = "=" * 80
    messages = [m.strip() for m in combined.split(separator) if m.strip()]

    logger.info("Skickar om %d meddelanden från loggen till Mattermost…", len(messages))
    sent = 0
    for message in messages:
        try:
            _post_to_mattermost(message)
            sent += 1
        except Exception:
            logger.exception("Misslyckades att skicka meddelande")
    logger.info("%d/%d meddelanden skickade om.", sent, len(messages))


def send_digest(results: list[AnalysisResult]) -> None:
    """Skicka ett Mattermost-inlägg per nyhet."""
    if not results:
        logger.info("Inga relevanta nyheter att skicka.")
        return

    sent = sum(1 for r in sorted(results, key=lambda x: x["score"], reverse=True) if send_result(r))
    logger.info("%d/%d nyheter skickade till Mattermost", sent, len(results))
