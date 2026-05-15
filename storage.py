"""SQLite-baserad lagring för att undvika dubbletter mellan körningar."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "seen_items.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Skapa databasen och tabeller om de inte finns."""
    with _get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_items (
                url TEXT PRIMARY KEY,
                seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # Rensa poster äldre än 30 dagar för att hålla databasen liten
        conn.execute(
            "DELETE FROM seen_items WHERE seen_at < datetime('now', '-30 days')"
        )
        conn.commit()


def is_seen(url: str) -> bool:
    """Returnerar True om URL:en redan har behandlats."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM seen_items WHERE url = ?", (url,)
        ).fetchone()
    return row is not None


def mark_seen(url: str) -> None:
    """Markera en URL som behandlad."""
    with _get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO seen_items (url) VALUES (?)", (url,)
        )
        conn.commit()


def mark_seen_batch(urls: list[str]) -> None:
    """Markera flera URL:er som behandlade."""
    with _get_conn() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO seen_items (url) VALUES (?)",
            [(u,) for u in urls],
        )
        conn.commit()
