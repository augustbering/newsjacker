"""Titelbaserad duplikatfiltrering för nyheter från flera källor.

Algoritm: Jaccard-likhet på signifikanta ord i titlarna.
Två nyheter räknas som duplikat om de delar >= SIMILARITY_THRESHOLD av sina ord.
Vid duplikat behålls den första förekomsten (vanligtvis den mest välkända källan).
"""
from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.5

# Svenska och engelska stoppord som inte bidrar till titelmatchning
_STOP_WORDS = {
    "att", "och", "i", "en", "ett", "av", "på", "för", "med", "är",
    "det", "den", "de", "som", "till", "om", "efter", "kan", "vi",
    "han", "hon", "har", "hade", "inte", "men", "från", "under",
    "mot", "ska", "upp", "ut", "in", "nu", "då", "när", "var",
    "the", "a", "an", "of", "in", "to", "and", "is", "for", "on",
    "at", "by", "with", "are", "was", "be", "has", "or", "that",
}


def _significant_words(title: str) -> frozenset[str]:
    """Normalisera titel och returnera signifikanta ord som en frozenset."""
    words = re.findall(r"[a-zåäöA-ZÅÄÖ]{3,}", title.lower())
    return frozenset(w for w in words if w not in _STOP_WORDS)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def deduplicate_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Ta bort duplikat baserat på titellikhet.

    Returnerar (unika, duplikat).
    """
    unique: list[dict] = []
    duplicates: list[dict] = []
    seen_word_sets: list[frozenset] = []

    for item in items:
        words = _significant_words(item.get("title", ""))
        is_dup = False
        for existing_words in seen_word_sets:
            if _jaccard(words, existing_words) >= SIMILARITY_THRESHOLD:
                is_dup = True
                break
        if is_dup:
            duplicates.append(item)
        else:
            unique.append(item)
            seen_word_sets.append(words)

    if duplicates:
        logger.info(
            "Titelduplikat borttagna: %d unika, %d duplikat",
            len(unique),
            len(duplicates),
        )

    return unique, duplicates
