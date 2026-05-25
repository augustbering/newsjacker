"""Central configuration – reads from .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

# Gemini
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "models/gemini-3-flash-preview")
DEEP_RESEARCH_AGENT: str = os.getenv("DEEP_RESEARCH_AGENT", "deep-research-pro-preview-12-2025")

# SMTP / e-post (ej längre primär notifieringskanal, behålls som fallback)
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM: str = os.getenv("EMAIL_FROM", SMTP_USER)
EMAIL_TO: str = os.getenv("EMAIL_TO", "")
EMAIL_CC: list[str] = [
    addr.strip()
    for addr in os.getenv("EMAIL_CC", "").split(",")
    if addr.strip()
]

# Mattermost webhook
MATTERMOST_WEBHOOK_URL: str = os.environ["MATTERMOST_WEBHOOK_URL"]

# Nitter – primär instans (kan överridas via .env)
NITTER_INSTANCE: str = os.getenv("NITTER_INSTANCE", "https://nitter.net")

KEYWORD_FILTER_ENABLED: bool = os.getenv("KEYWORD_FILTER_ENABLED", "true").lower() in ("1", "true", "yes")
# Fallback-instanser om primär inte svarar (testas i ordning)
NITTER_FALLBACKS: list[str] = [
    inst.strip()
    for inst in os.getenv(
        "NITTER_FALLBACKS",
        "https://nitter.poast.org,https://nitter.privacydev.net,https://nitter.1d4.us",
    ).split(",")
    if inst.strip()
]

# Agent-inställningar
RELEVANCE_THRESHOLD: int = int(os.getenv("RELEVANCE_THRESHOLD", "6"))
SCHEDULE_HOURS: int = int(os.getenv("SCHEDULE_HOURS", "2"))

# RSS-källor
RSS_FEEDS: list[dict] = [
    {"name": "SVT Nyheter", "url": "https://www.svt.se/nyheter/rss.xml"},
    {"name": "DN", "url": "https://www.dn.se/rss/"},
    {"name": "Aftonbladet", "url": "https://rss.aftonbladet.se/rss2/small/pages/sections/senastenytt/"},
    {"name": "Expressen", "url": "https://feeds.expressen.se/nyheter/"},
    {"name": "Omni", "url": "https://omni.se/a/rss.xml"},
    {"name": "IDG.se", "url": "https://www.idg.se/rss/"},
    {"name": "Computer Sweden", "url": "https://computersweden.idg.se/rss/"},
    {"name": "Göteborgs-Posten", "url": "https://www.gp.se/rss/"},
    {"name": "Sydsvenskan", "url": "https://www.sydsvenskan.se/feeds/feed.xml"},
    {"name": "Dagens Industri", "url": "https://www.di.se/rss"},
    {"name": "Sveriges Radio Ekot", "url": "http://api.sr.se/api/rss/program/83"},
]

# Söktermer för Nitter/Twitter
NITTER_SEARCH_TERMS: list[str] = [
    "#svpol",
    "#dataintegritet",
    "#upphovsrätt",
    "#piratpartiet",
    "#övervakningssamhället",
    "#FRA",
    "#signalspaning",
    "#AI",
    "#personuppgifter",
    "#GDPR",
    "#yttrandefrihet",
    "#kryptering",
    "#nätneutralitet",
    "integritet lag",
    "övervakning polis",
    "upphovsrätt reform",
]

# Piratpartiets kärnfrågor – används som kontext i AI-prompten
PARTY_CONTEXT = """
Piratpartiet är ett politiskt parti i Sverige med fokus på:
- Basinkomst och ekonomisk rättvisa. AI kommer leda till massarbetslöshet, så vi förespråkar basinkomst som trygghet för alla.
- Avkriminalisering av drogbruk och en mer human narkotikapolitik.
- Personlig integritet och motstånd mot massövervakning (FRA-lagen, Säpo, kameraövervakning)
- Reform av upphovsrätt och immaterialrätt – fri kultur och Creative Commons
- Internets frihet, nätneutralitet och motstånd mot censur
- Transparens i offentlig förvaltning och öppna data
- Stärkt skydd för visselblåsare och journalisters källor
- Kryptering och digitala rättigheter
- Kritisk granskning av AI-lagstiftning och algoritmers makt
- Läkemedels- och patentreform
- Decentralisering och motståndet mot teknologimonopol
""".strip()
