"""Build-time Strong's-lexicon loader — ingest of the committed STEPBible TBESG lexicon.

Reads lexicon JSON from a committed ``data/strongs/`` directory (one file per source; currently
``lexicon.json``, produced by ``scripts/convert_strongs_lexicon.py``) and populates the additive
``strongs_entries`` table. The lexical analogue of the topical loader: a build-time, idempotent
data load baked into ``bible.db``.

**Input contract (per lexicon JSON file).** One file describes one source's entries::

    {
      "source": "STEP Bible (Tyndale House)",
      "entries": [
        {
          "strongs_id": "G26",          # collapsed-base Strong's number (PRIMARY KEY)
          "language": "grc",            # ISO 639-3
          "lemma": "ἀγάπη",
          "transliteration": "agapē",
          "gloss": "love",              # brief meaning
          "definition": "ἀγάπη, -ης, ἡ … love, goodwill, esteem. …"
        }
      ]
    }

Strong's ids are unique per build (duplicate → ``LoaderError``). Deterministic (files sorted,
entries in array order) → byte-identical rebuilds. Pure stdlib (``json`` + ``sqlite3``) —
``bible-core`` stays web-free and ML-free.
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

# (strongs_id, language, lemma, transliteration, gloss, definition, source)
StrongsEntryRow = tuple[str, str, str, str, str, str, str]
# (text_id, book_id, chapter, verse, position, surface_form, strongs_id, morph_code)
WordTokenRow = tuple[str, str, int, int, int, str, str | None, str | None]


@dataclass(frozen=True)
class StrongsStats:
    """Summary of a completed Strong's-lexicon load."""

    strongs_entries: int


@dataclass(frozen=True)
class WordTokensStats:
    """Summary of a completed word-tokens load."""

    word_tokens: int
    tokens_skipped: int


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


def _opt_str(obj: Any, key: str, ctx: str) -> str:
    """A string that may be empty (e.g. transliteration is absent for some extended entries)."""
    value = _get(obj, key, ctx)
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string.")
    return value


def _req_int(obj: Any, key: str, ctx: str) -> int:
    value = _get(obj, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def _nullable_str(obj: Any, key: str, ctx: str) -> str | None:
    """A string that may be JSON ``null`` (an untagged token's strongs_id / morph_code)."""
    if not isinstance(obj, dict):
        raise LoaderError(f"{ctx}: expected a JSON object, got {type(obj).__name__}.")
    value = cast("dict[str, Any]", obj).get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise LoaderError(f"{ctx}: field {key!r} must be a string or null.")
    return value


def discover_lexicon_files(lexicon_dir: Path) -> list[Path]:
    """Return every lexicon ``*.json`` directly under ``lexicon_dir``, in deterministic order.

    The ``tokens-*.json`` files (loaded separately into ``word_tokens``) share this directory, so
    they are excluded here."""
    if not lexicon_dir.is_dir():
        return []
    return sorted(
        (p for p in lexicon_dir.glob("*.json") if not p.name.startswith("tokens-")),
        key=lambda p: str(p),
    )


def parse_lexicon_file(path: Path) -> list[StrongsEntryRow]:
    """Parse one lexicon JSON file into entry rows."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    source = _req_str(raw, "source", path.name)
    entries = _get(raw, "entries", path.name)
    if not isinstance(entries, list):
        raise LoaderError(f"{path.name}: 'entries' must be a list.")

    rows: list[StrongsEntryRow] = []
    for index, entry in enumerate(cast("list[Any]", entries)):
        ctx = f"{path.name} entries[{index}]"
        rows.append(
            (
                _req_str(entry, "strongs_id", ctx),
                _req_str(entry, "language", ctx),
                _req_str(entry, "lemma", ctx),
                _opt_str(entry, "transliteration", ctx),
                _req_str(entry, "gloss", ctx),
                _req_str(entry, "definition", ctx),
                source,
            )
        )
    return rows


def load_strongs_entries(conn: sqlite3.Connection, lexicon_dir: Path) -> StrongsStats:
    """Ingest lexicon JSON from ``lexicon_dir`` into ``strongs_entries``. A missing/empty directory
    loads nothing — not an error."""
    rows: list[StrongsEntryRow] = []
    seen_ids: set[str] = set()
    for path in discover_lexicon_files(lexicon_dir):
        for row in parse_lexicon_file(path):
            if row[0] in seen_ids:
                raise LoaderError(f"{path.name}: duplicate Strong's id {row[0]!r}.")
            seen_ids.add(row[0])
            rows.append(row)

    conn.executemany(
        "INSERT INTO strongs_entries "
        "(strongs_id, language, lemma, transliteration, gloss, definition, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return StrongsStats(strongs_entries=len(rows))


def discover_token_files(tokens_dir: Path) -> list[Path]:
    """Return every ``tokens-*.json`` directly under ``tokens_dir``, in deterministic order.

    The ``tokens-`` prefix keeps the lexicon file (``lexicon.json``) and the token files in the
    same ``data/strongs/`` directory without the two loaders reading each other's files."""
    if not tokens_dir.is_dir():
        return []
    return sorted(tokens_dir.glob("tokens-*.json"), key=lambda p: str(p))


def parse_tokens_file(
    path: Path, alias_to_book: dict[str, str], stats: Counter[str]
) -> list[WordTokenRow]:
    """Parse one tokens JSON file into word-token rows; unresolved books are skipped + counted."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    text_id = _req_str(raw, "text_id", path.name)
    tokens = _get(raw, "tokens", path.name)
    if not isinstance(tokens, list):
        raise LoaderError(f"{path.name}: 'tokens' must be a list.")

    rows: list[WordTokenRow] = []
    for index, token in enumerate(cast("list[Any]", tokens)):
        ctx = f"{path.name} tokens[{index}]"
        book_id = alias_to_book.get(normalize(_req_str(token, "book", ctx)))
        if book_id is None:
            stats["tokens_skipped"] += 1
            continue
        chapter = _req_int(token, "chapter", ctx)
        verse = _req_int(token, "verse", ctx)
        position = _req_int(token, "position", ctx)
        if chapter < 1 or verse < 1 or position < 1:
            raise LoaderError(f"{ctx}: chapter, verse and position must be positive.")
        rows.append(
            (
                text_id,
                book_id,
                chapter,
                verse,
                position,
                _req_str(token, "surface_form", ctx),
                _nullable_str(token, "strongs_id", ctx),
                _nullable_str(token, "morph_code", ctx),
            )
        )
    return rows


def load_word_tokens(
    conn: sqlite3.Connection, tokens_dir: Path, alias_to_book: dict[str, str]
) -> WordTokensStats:
    """Ingest token JSON from ``tokens_dir`` into ``word_tokens``. A missing/empty directory loads
    nothing — not an error. The composite PK dedups; ``OR IGNORE`` keeps the load robust."""
    rows: list[WordTokenRow] = []
    stats: Counter[str] = Counter()
    for path in discover_token_files(tokens_dir):
        rows.extend(parse_tokens_file(path, alias_to_book, stats))

    conn.executemany(
        "INSERT OR IGNORE INTO word_tokens "
        "(text_id, book_id, chapter, verse, position, surface_form, strongs_id, morph_code) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    inserted = conn.execute("SELECT COUNT(*) FROM word_tokens").fetchone()[0]
    return WordTokensStats(word_tokens=inserted, tokens_skipped=stats["tokens_skipped"])
