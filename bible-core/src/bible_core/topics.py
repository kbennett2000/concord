"""Build-time topical-Bible loader — ingest of the committed Nave's Topical Bible dataset.

Reads topic JSON from a committed ``data/topics/`` directory (one file per source; currently
``naves.json``, produced by ``scripts/convert_naves_topics.py``) and populates the additive
``topics`` + ``topic_verses`` tables. The topical analogue of the geography loader: a build-time,
idempotent data load baked into ``bible.db``.

**Input contract (per topics JSON file).** One file describes one source's topics::

    {
      "source": "Nave's Topical Bible",
      "topics": [
        {
          "id": "care",                 # stable slug (PRIMARY KEY)
          "name": "CARE",               # subject heading
          "section": "C",               # A-Z index letter
          "see_also": "anxiety",        # optional: a "See X" redirect target's id (else null)
          "verses": [                   # canonical verse links (book is a code/alias)
            {"book": "PHP", "chapter": 4, "verse": 6}
          ]
        }
      ]
    }

Verse ``book`` is resolved through the seeded alias table; an unresolvable link is **skipped and
counted** (the committed data is pre-resolved, so this is defensive). The composite PK on
``topic_verses`` dedups repeated links for free. Topic ids are unique per build (duplicate →
``LoaderError``). Deterministic (files sorted, topics/verses in array order) → byte-identical
rebuilds. Pure stdlib (``json`` + ``sqlite3``) — ``bible-core`` stays web-free and ML-free.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .loader import LoaderError
from .normalize import normalize

# (id, name, section, see_also, source)
TopicRow = tuple[str, str, str, str | None, str]
# (topic_id, book_id, chapter, verse)
TopicVerseRow = tuple[str, str, int, int]


@dataclass(frozen=True)
class TopicsStats:
    """Summary of a completed topics load."""

    topics: int
    topic_verses: int
    redirects: int
    verse_links_skipped: int


def _get(obj: Any, key: str, ctx: str) -> Any:
    if not isinstance(obj, dict):
        raise LoaderError(f"{ctx}: expected a JSON object, got {type(obj).__name__}.")
    mapping = cast("dict[str, Any]", obj)
    if key not in mapping:
        raise LoaderError(f"{ctx}: missing required field {key!r}.")
    return mapping[key]


def _req_str(obj: Any, key: str, ctx: str) -> str:
    value = _get(obj, key, ctx)
    if not isinstance(value, str) or not value:
        raise LoaderError(f"{ctx}: field {key!r} must be a non-empty string.")
    return value


def _req_int(obj: Any, key: str, ctx: str) -> int:
    value = _get(obj, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def discover_topic_files(topics_dir: Path) -> list[Path]:
    """Return every ``*.json`` directly under ``topics_dir``, in deterministic order."""
    if not topics_dir.is_dir():
        return []
    return sorted(topics_dir.glob("*.json"), key=lambda p: str(p))


def parse_topics_file(
    path: Path, alias_to_book: dict[str, str], stats: Counter[str]
) -> tuple[list[TopicRow], list[TopicVerseRow]]:
    """Parse one topics JSON file into topic rows + verse-link rows."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    source = _req_str(raw, "source", path.name)
    topic_rows: list[TopicRow] = []
    verse_rows: list[TopicVerseRow] = []
    topics = _get(raw, "topics", path.name)
    if not isinstance(topics, list):
        raise LoaderError(f"{path.name}: 'topics' must be a list.")
    for index, topic in enumerate(cast("list[Any]", topics)):
        ctx = f"{path.name} topics[{index}]"
        topic_id = _req_str(topic, "id", ctx)
        name = _req_str(topic, "name", ctx)
        section = _req_str(topic, "section", ctx)
        topic_obj = cast("dict[str, Any]", topic)
        see_also_raw = topic_obj.get("see_also")
        see_also = see_also_raw if isinstance(see_also_raw, str) and see_also_raw else None
        topic_rows.append((topic_id, name, section, see_also, source))
        if see_also is not None:
            stats["redirects"] += 1

        links: Any = topic_obj.get("verses")
        if links is None:
            links = []
        if not isinstance(links, list):
            raise LoaderError(f"{ctx}: 'verses' must be a list.")
        for vi, link in enumerate(cast("list[Any]", links)):
            v_ctx = f"{ctx} verses[{vi}]"
            book_id = alias_to_book.get(normalize(_req_str(link, "book", v_ctx)))
            chapter = _req_int(link, "chapter", v_ctx)
            verse = _req_int(link, "verse", v_ctx)
            if book_id is None:
                stats["verse_links_skipped"] += 1
                continue
            if chapter < 1 or verse < 1:
                raise LoaderError(f"{v_ctx}: chapter and verse must be positive.")
            verse_rows.append((topic_id, book_id, chapter, verse))

    return topic_rows, verse_rows


def load_topics(
    conn: sqlite3.Connection, topics_dir: Path, alias_to_book: dict[str, str]
) -> TopicsStats:
    """Ingest topic JSON from ``topics_dir`` into ``topics`` / ``topic_verses``. A missing/empty
    directory loads nothing — not an error."""
    topic_rows: list[TopicRow] = []
    verse_rows: list[TopicVerseRow] = []
    stats: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for path in discover_topic_files(topics_dir):
        topics, verses = parse_topics_file(path, alias_to_book, stats)
        for row in topics:
            if row[0] in seen_ids:
                raise LoaderError(f"{path.name}: duplicate topic id {row[0]!r}.")
            seen_ids.add(row[0])
        topic_rows.extend(topics)
        verse_rows.extend(verses)

    conn.executemany(
        "INSERT INTO topics (id, name, section, see_also, source) VALUES (?, ?, ?, ?, ?)",
        topic_rows,
    )
    # PK (topic_id, book_id, chapter, verse) dedups repeated links; OR IGNORE keeps the load
    # robust to a topic that cites the same verse twice across its sub-headings.
    conn.executemany(
        "INSERT OR IGNORE INTO topic_verses (topic_id, book_id, chapter, verse) "
        "VALUES (?, ?, ?, ?)",
        verse_rows,
    )
    inserted_links = conn.execute("SELECT COUNT(*) FROM topic_verses").fetchone()[0]
    return TopicsStats(
        topics=len(topic_rows),
        topic_verses=inserted_links,
        redirects=stats["redirects"],
        verse_links_skipped=stats["verse_links_skipped"],
    )
