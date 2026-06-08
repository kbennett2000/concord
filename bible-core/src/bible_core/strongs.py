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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .loader import LoaderError

# (strongs_id, language, lemma, transliteration, gloss, definition, source)
StrongsEntryRow = tuple[str, str, str, str, str, str, str]


@dataclass(frozen=True)
class StrongsStats:
    """Summary of a completed Strong's-lexicon load."""

    strongs_entries: int


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


def discover_lexicon_files(lexicon_dir: Path) -> list[Path]:
    """Return every ``*.json`` directly under ``lexicon_dir``, in deterministic order."""
    if not lexicon_dir.is_dir():
        return []
    return sorted(lexicon_dir.glob("*.json"), key=lambda p: str(p))


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
