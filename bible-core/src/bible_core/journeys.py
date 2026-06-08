"""Build-time journeys loader — ingest of the committed curated-itineraries dataset.

Reads journey JSON from a committed ``data/journeys/`` directory (one file per source; currently
``journeys.json``, hand-authored) and populates the additive ``journeys`` + ``journey_stops``
tables. The route-level analogue of the geography loader: a build-time, idempotent data load
baked into ``bible.db``.

**Reuses v3 geography — never rebuilds it.** Each stop's ``place_id`` is a foreign key into the
EXISTING ``places`` table; the loader validates every ``place_id`` against the already-loaded
places and **fails loud** on an unknown one (the data is hand-curated, so an unresolved place is a
data bug, not a tolerable skip). Journeys are ONE proposed reconstruction (SPEC v7) — the
``source`` + ``note`` fields carry that honesty; competing routes are deliberately not modeled.

**Input contract (per journeys JSON file).** One file describes one or more journeys::

    {
      "journeys": [
        {
          "id": "paul-first",                       # stable slug (PRIMARY KEY)
          "name": "Paul's First Missionary Journey",
          "scripture": "Acts 13-14",                # overall narrative range
          "dating": "c. AD 46-48 (conventional)",   # optional; null when genuinely debated
          "source": "Itinerary from Acts 13-14; places from OpenBible.info.",
          "note": "One commonly proposed reconstruction following the sequence of Acts.",
          "stops": [                                 # ORDERED; place_id is a FK into places
            {"ordinal": 1, "place_id": "ae41ab4", "reference": "Acts 13:1"}
          ]
        }
      ]
    }

A stop's ``place_id`` must exist in ``places`` (else ``LoaderError``); ``reference`` is optional
free text. Ordinals must be unique within a journey; ``stops`` must be non-empty; journey ids are
unique per build (duplicate → ``LoaderError``). Deterministic (files sorted, journeys/stops in
array order) → byte-identical rebuilds. Pure stdlib (``json`` + ``sqlite3``) — ``bible-core`` stays
web-free and ML-free.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .loader import LoaderError

# (id, name, scripture, dating, source, note)
JourneyRow = tuple[str, str, str, str | None, str, str]
# (journey_id, ordinal, place_id, reference)
JourneyStopRow = tuple[str, int, str, str | None]


@dataclass(frozen=True)
class JourneyStats:
    """Summary of a completed journeys load."""

    journeys: int
    journey_stops: int


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


def _opt_str(obj: Any, key: str, ctx: str) -> str | None:
    """An optional string: absent/null → None; present must be a non-empty string."""
    mapping = cast("dict[str, Any]", obj)
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise LoaderError(f"{ctx}: field {key!r} must be a non-empty string when present.")
    return value


def _req_int(obj: Any, key: str, ctx: str) -> int:
    value = _get(obj, key, ctx)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LoaderError(f"{ctx}: field {key!r} must be an integer, got {type(value).__name__}.")
    return value


def discover_journey_files(journeys_dir: Path) -> list[Path]:
    """Return every ``*.json`` directly under ``journeys_dir``, in deterministic order."""
    if not journeys_dir.is_dir():
        return []
    return sorted(journeys_dir.glob("*.json"), key=lambda p: str(p))


def parse_journeys_file(path: Path) -> tuple[list[JourneyRow], list[JourneyStopRow]]:
    """Parse one journeys JSON file into journey rows + ordered stop rows.

    Validates structure but not ``place_id`` existence — that needs the loaded ``places`` table
    and is checked in :func:`load_journeys`.
    """
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LoaderError(f"{path.name}: invalid JSON ({exc}).") from exc

    journey_rows: list[JourneyRow] = []
    stop_rows: list[JourneyStopRow] = []
    journeys = _get(raw, "journeys", path.name)
    if not isinstance(journeys, list):
        raise LoaderError(f"{path.name}: 'journeys' must be a list.")
    for index, journey in enumerate(cast("list[Any]", journeys)):
        ctx = f"{path.name} journeys[{index}]"
        journey_id = _req_str(journey, "id", ctx)
        name = _req_str(journey, "name", ctx)
        scripture = _req_str(journey, "scripture", ctx)
        dating = _opt_str(journey, "dating", ctx)
        source = _req_str(journey, "source", ctx)
        note = _req_str(journey, "note", ctx)
        journey_rows.append((journey_id, name, scripture, dating, source, note))

        stops = _get(journey, "stops", ctx)
        if not isinstance(stops, list) or not stops:
            raise LoaderError(f"{ctx}: 'stops' must be a non-empty list.")
        seen_ordinals: set[int] = set()
        for si, stop in enumerate(cast("list[Any]", stops)):
            s_ctx = f"{ctx} stops[{si}]"
            ordinal = _req_int(stop, "ordinal", s_ctx)
            if ordinal < 1:
                raise LoaderError(f"{s_ctx}: 'ordinal' must be positive.")
            if ordinal in seen_ordinals:
                raise LoaderError(f"{ctx}: duplicate ordinal {ordinal}.")
            seen_ordinals.add(ordinal)
            place_id = _req_str(stop, "place_id", s_ctx)
            reference = _opt_str(stop, "reference", s_ctx)
            stop_rows.append((journey_id, ordinal, place_id, reference))

    return journey_rows, stop_rows


def load_journeys(conn: sqlite3.Connection, journeys_dir: Path) -> JourneyStats:
    """Ingest journey JSON from ``journeys_dir`` into ``journeys`` / ``journey_stops``.

    A missing/empty directory loads nothing — not an error. Every stop's ``place_id`` is
    validated against the already-loaded ``places`` table; an unknown id raises ``LoaderError``
    (hand-curated data must reference real geography). Run AFTER :func:`bible_core.geo.load_places`.
    """
    journey_rows: list[JourneyRow] = []
    stop_rows: list[JourneyStopRow] = []
    seen_ids: set[str] = set()
    for path in discover_journey_files(journeys_dir):
        journeys, stops = parse_journeys_file(path)
        for row in journeys:
            if row[0] in seen_ids:
                raise LoaderError(f"{path.name}: duplicate journey id {row[0]!r}.")
            seen_ids.add(row[0])
        journey_rows.extend(journeys)
        stop_rows.extend(stops)

    known_places = {r[0] for r in conn.execute("SELECT id FROM places").fetchall()}
    for journey_id, ordinal, place_id, _reference in stop_rows:
        if place_id not in known_places:
            raise LoaderError(
                f"journey {journey_id!r} stop {ordinal}: unknown place_id {place_id!r} "
                "(not in the places table)."
            )

    conn.executemany(
        "INSERT INTO journeys (id, name, scripture, dating, source, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        journey_rows,
    )
    conn.executemany(
        "INSERT INTO journey_stops (journey_id, ordinal, place_id, reference) VALUES (?, ?, ?, ?)",
        stop_rows,
    )
    return JourneyStats(journeys=len(journey_rows), journey_stops=len(stop_rows))
