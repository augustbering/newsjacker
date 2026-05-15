"""Nyckelordsfilter – grovgallring innan Gemini-anrop för att spara API-kvot."""
from __future__ import annotations

import re

# Nyckelord grupperade per ämne – minst ett ord i en grupp måste matcha.
# Matchning är skiftlägesokänslig och ordgränsbaserad.
KEYWORD_GROUPS: list[list[str]] = [
    # Basinkomst & ekonomisk rättvisa
    ["basinkomst", "medborgarlön", "universell grundinkomst","omställning","vidareutbildning","omskolning","AI-jobb","AI-ersättning"],
    # Avkriminalisering & narkotikapolitik
    ["avkriminalisering", "narkotikapolitik", "cannabis", "drogpolitik", "legalisering", "harm reduction", "sprutbyte", "naloxon","gängskjutning","gängvåld"],
    # Integritet & övervakning
    ["integritet", "personuppgift", "övervakning", "spionage", "avlyssning",
     "kamera", "FRA", "signalspaning", "säkerhetspolisen", "Säpo",
     "datalagring", "metadata", "biometri", "ansiktsigenkänning"],

    # Upphovsrätt & kultur
    ["upphovsrätt", "copyright", "fildelning", "piratkopiering", "Creative Commons",
     "patent", "immaterialrätt", "licensiering", "streaming-rättigheter",
     "olovlig kopiering", "upphovsrättsbrott"],

    # Internet & censur
    ["censur", "nätneutralitet", "internetfrihet", "blockering", "filtrering",
     "DNS-blockad", "geoblockning", "darknet", "Tor", "VPN"],

    # Kryptering & cybersäkerhet
    ["kryptering", "bakdörr", "Signal", "cybersäkerhet", "cyberhot",
     "dataintrång", "ransomware", "hackare", "sårbarhet", "exploit",
     "säkerhetsbrister", "HTTPS", "end-to-end"],

    # AI & digitala rättigheter
    ["artificiell intelligens", "AI-lag", "algoritm", "automatiserat beslut",
     "deepfake", "ansiktsigenkänning AI", "AI-etik", "AI-reglering"],

    # Transparens & visselblåsare
    ["visselblåsare", "whistleblower", "offentlighetsprincipen", "sekretess",
     "läcka", "transparens", "öppna data", "Julian Assange", "Wikileaks"],

    # Läkemedel & patent
    ["läkemedelspatent", "generika", "patentskydd", "läkemedelspris",
     "vaccin-patent", "farmaceutisk"],

    # Digitalpolitik
    ["GDPR", "dataskydd", "NIS2", "EU-AI-akt", "Digital Services Act",
     "Digital Markets Act", "eIDAS", "chat control", "CSAM-scanning"],
]

# Platta ut till en enda mängd för snabb sökning
_ALL_KEYWORDS: list[str] = [kw for group in KEYWORD_GROUPS for kw in group]


def _compile_pattern(keywords: list[str]) -> re.Pattern:
    escaped = [r"\b" + re.escape(kw) + r"\b" for kw in keywords]
    return re.compile("|".join(escaped), re.IGNORECASE)


_PATTERN = _compile_pattern(_ALL_KEYWORDS)


def is_relevant(title: str, summary: str = "") -> bool:
    """Returnerar True om texten innehåller minst ett nyckelord."""
    text = f"{title} {summary}"
    return bool(_PATTERN.search(text))


def filter_items(items: list[dict]) -> tuple[list[dict], list[dict]]:
    """Dela upp items i (passar_filter, filtrerade_bort)."""
    passed, dropped = [], []
    for item in items:
        title = item.get("title", "") or item.get("text", "")
        summary = item.get("summary", "") or item.get("text", "")
        if is_relevant(title, summary):
            passed.append(item)
        else:
            dropped.append(item)
    return passed, dropped
