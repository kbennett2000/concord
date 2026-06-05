"""Build-time geography loader — disciplined ingest of OpenBible's Bible-Geocoding-Data.

Reads ``ancient.jsonl`` (biblical places, with verse links and confidence) + ``modern.jsonl``
(modern locations with coordinates) from a committed ``data/geography/`` directory and
populates the additive ``places`` + ``place_verses`` tables (SPEC v3 §4-§6). The v3 analogue
of v1's cross-reference loader: a build-time, idempotent data load baked into ``bible.db``.

**Extraction discipline (SPEC v3 §4).** The source dataset is far richer than we need. This
loader extracts a *small, deliberate subset* — id, friendly_id, a derived display name +
slug, type, article, best coordinates + confidence, status, and verse links — and
**deliberately ignores** the scholarly apparatus: time-weighted scores, resolution paths,
isoband/polygon geometry, images, linked-data, the 400+ sources, EPSG-28191 grid coordinates,
and the per-translation spelling apparatus beyond verse-linking.

**Field reality (verified against the live dataset).** The data's field *shapes* differ from
their labels: top-level ``name`` and ``type`` (singular) are ``null`` for every record, so the
display name is derived from ``friendly_id`` (trailing disambiguation index stripped) and the
type is taken from the ``types`` array. ``modern.jsonl``'s ``lonlat`` is ``"longitude,latitude"``
order (longitude first).

**Honesty model — two independent axes (SPEC v3 §6).**
- ``confidence`` (high/medium/low) = *evidence strength*, bucketed from the best association's
  adjusted score: high ≥ 500, medium 100-499, low < 100 (negatives included as low).
- ``status`` (identified/disputed/unknown/symbolic/multiple) = the *resolution kind*:
  * a **semantic** special marker on the place — ``unknown_place``, ``nonspecific_place``,
    ``multiple_locations`` — suppresses coordinates (the honesty model) and sets
    unknown/symbolic/multiple, taking precedence over any tentative association;
  * otherwise a real modern association locates the place: a **net-negative** or **competing**
    best score → ``disputed``; else ``identified``. ``recursive`` is a resolution-path
    artifact, *not* a semantic claim, so it never voids a real association — a recursive-only
    place with no association is honestly ``unknown``.

Pure stdlib (``json`` + ``sqlite3`` + ``re``) — ``bible-core`` stays web-free and ML-free.
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

# Confidence buckets, calibrated against the real adjusted-score distribution (median ≈ 577,
# observed range −87..1169). SPEC v3 §6.
HIGH_SCORE = 500
MEDIUM_SCORE = 100

# A runner-up association within this fraction of the top score (and both meaningfully
# positive) is a genuine near-tie → the identification is contested → ``disputed``.
COMPETING_RATIO = 0.8
COMPETING_MIN = 100

# Semantic special markers (in precedence order) suppress coordinates and set the status.
# ``recursive`` is deliberately excluded — it is a resolution-path artifact, not a claim
# about the place. ``not_a_place``/``not_a_proper_name`` drive exclusion, not a status.
_SEMANTIC_STATUS: tuple[tuple[str, str], ...] = (
    ("unknown_place", "unknown"),
    ("multiple_locations", "multiple"),
    ("nonspecific_place", "symbolic"),
)
_NON_PLACE_SPECIALS = frozenset({"not_a_place", "not_a_proper_name"})

# (place_id, book_id, chapter, verse)
PlaceVerseRow = tuple[str, str, int, int]
# (id, friendly_id, name, url_slug, type, preceding_article,
#  latitude, longitude, confidence, confidence_score, status, modern_name)
PlaceRow = tuple[
    str,
    str,
    str,
    str,
    str,
    str,
    float | None,
    float | None,
    str | None,
    int | None,
    str,
    str | None,
]


@dataclass(frozen=True)
class GeoStats:
    """Summary of a completed geography load."""

    places: int
    place_verses: int
    places_excluded: int
    verse_links_skipped: int
    by_status: dict[str, int]


# --- JSONL reading -------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Parse a JSON Lines file into a list of objects. Fails loudly on malformed input."""
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj: Any = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LoaderError(f"{path.name}:{line_no}: invalid JSON ({exc}).") from exc
            if not isinstance(obj, dict):
                raise LoaderError(f"{path.name}:{line_no}: expected a JSON object.")
            records.append(cast("dict[str, Any]", obj))
    return records


def load_modern_lonlats(modern_path: Path) -> dict[str, tuple[float, float]]:
    """Map each modern location id → (longitude, latitude) from ``modern.jsonl``.

    ``lonlat`` is ``"longitude,latitude"`` order — longitude first. Records without a usable
    ``lonlat`` are simply absent from the map (a place referencing them gets no coordinate).
    """
    lonlats: dict[str, tuple[float, float]] = {}
    for record in _read_jsonl(modern_path):
        modern_id = record.get("id")
        lonlat = record.get("lonlat")
        if not isinstance(modern_id, str) or not isinstance(lonlat, str):
            continue
        parts = lonlat.split(",")
        if len(parts) != 2:
            continue
        try:
            longitude, latitude = float(parts[0]), float(parts[1])
        except ValueError:
            continue
        lonlats[modern_id] = (longitude, latitude)
    return lonlats


# --- field derivation ----------------------------------------------------------------


def _display_name(friendly_id: str) -> str:
    """Strip a trailing disambiguation index ("Aroer 2" → "Aroer"; "Jerusalem" → "Jerusalem")."""
    base = friendly_id.rsplit(" ", 1)
    if len(base) == 2 and base[1].isdigit():
        return base[0]
    return friendly_id


def _place_type(record: dict[str, Any]) -> str:
    """The place type, from the ``types`` array (top-level ``type`` is null in the data)."""
    types = record.get("types")
    if isinstance(types, list) and types and isinstance(types[0], str):
        return types[0]
    return "unknown"


def _collect_specials(record: dict[str, Any]) -> set[str]:
    """All ``special`` resolution markers present anywhere in the place's identifications."""
    specials: set[str] = set()
    identifications = record.get("identifications")
    if not isinstance(identifications, list):
        return specials
    for identification in cast("list[Any]", identifications):
        if not isinstance(identification, dict):
            continue
        resolutions = cast("dict[str, Any]", identification).get("resolutions")
        if not isinstance(resolutions, list):
            continue
        for resolution in cast("list[Any]", resolutions):
            if isinstance(resolution, dict):
                special = cast("dict[str, Any]", resolution).get("special")
                if isinstance(special, str):
                    specials.add(special)
    return specials


def _score(assoc: dict[str, Any]) -> int:
    value = assoc.get("score", 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _best_located_association(
    modern_associations: dict[str, Any], lonlats: dict[str, tuple[float, float]]
) -> tuple[dict[str, Any], tuple[float, float], list[int]] | None:
    """The highest-scoring association that carries a coordinate, its lonlat, and all scores.

    Ties are broken deterministically (highest score, then lowest modern id) so the build is
    reproducible. Returns ``None`` when the place has no association carrying a coordinate.
    """
    located: list[tuple[int, str, dict[str, Any], tuple[float, float]]] = []
    all_scores: list[int] = []
    for modern_id, assoc in modern_associations.items():
        if not isinstance(assoc, dict):
            continue
        typed = cast("dict[str, Any]", assoc)
        all_scores.append(_score(typed))
        coord = lonlats.get(modern_id)
        if coord is not None:
            located.append((_score(typed), modern_id, typed, coord))
    if not located:
        return None
    # Deterministic: sort by modern id ascending, then take the max score — max() returns the
    # first maximal element, so ties resolve to the lowest modern id.
    located.sort(key=lambda item: item[1])
    best = max(located, key=lambda item: item[0])
    return best[2], best[3], sorted(all_scores, reverse=True)


def _confidence_bucket(score: int) -> str:
    if score >= HIGH_SCORE:
        return "high"
    if score >= MEDIUM_SCORE:
        return "medium"
    return "low"


@dataclass(frozen=True)
class _Derived:
    latitude: float | None
    longitude: float | None
    confidence: str | None
    confidence_score: int | None
    status: str
    modern_name: str | None


def _derive(
    specials: set[str],
    modern_associations: dict[str, Any],
    lonlats: dict[str, tuple[float, float]],
) -> _Derived | None:
    """Apply the two-axis honesty model. Returns ``None`` when the place is excluded."""
    # 1. A semantic special claim about the place suppresses coordinates (honesty model),
    #    taking precedence over any tentative association.
    for marker, status in _SEMANTIC_STATUS:
        if marker in specials:
            return _Derived(None, None, None, None, status, None)

    # 2. A real, located modern association places the place.
    best = _best_located_association(modern_associations, lonlats)
    if best is not None:
        assoc, (longitude, latitude), scores = best
        top = scores[0]
        runner_up = scores[1] if len(scores) >= 2 else None
        modern_name = assoc.get("name") if isinstance(assoc.get("name"), str) else None
        competing = (
            runner_up is not None
            and top >= COMPETING_MIN
            and runner_up >= COMPETING_MIN
            and runner_up >= COMPETING_RATIO * top
        )
        # net-negative best score: the weight of scholarship judges the identification wrong;
        # competing: a near-tie runner-up means the identification is genuinely contested.
        status = "disputed" if (top < 0 or competing) else "identified"
        return _Derived(latitude, longitude, _confidence_bucket(top), top, status, modern_name)

    # 3. No semantic special and no located association.
    if "recursive" in specials:  # an unresolvable resolution loop → honestly unknown
        return _Derived(None, None, None, None, "unknown", None)
    if specials and specials <= _NON_PLACE_SPECIALS:  # purely "not a place" → exclude
        return None
    return _Derived(None, None, None, None, "unknown", None)  # defensive (unobserved)


# --- verse mapping -------------------------------------------------------------------


def _map_verse(
    verse: dict[str, Any], order_to_book: dict[int, str], alias_to_book: dict[str, str]
) -> tuple[str, int, int] | None:
    """Map one ``verses[]`` entry to (book_id, chapter, verse), or ``None`` to skip.

    Primary: the ``sort`` key (BBCCCVVV, BB = 01 Genesis … 66 Revelation → canonical order).
    Fallback: ``osis`` (Book.Chapter.Verse) via the book aliases. The human-readable
    ``readable`` string is never parsed. A reference outside the seeded 1-66 canon (e.g. a
    stray deuterocanonical verse) is skipped and counted — not fatal.
    """
    sort = verse.get("sort")
    if isinstance(sort, str) and len(sort) == 8 and sort.isdigit():
        book_id = order_to_book.get(int(sort[0:2]))
        chapter, verse_num = int(sort[2:5]), int(sort[5:8])
        if book_id is not None and chapter >= 1 and verse_num >= 1:
            return book_id, chapter, verse_num
        if book_id is None:
            return None  # out-of-canon book → skip

    osis = verse.get("osis")  # fallback
    if isinstance(osis, str):
        parts = osis.split(".")
        if len(parts) == 3:
            book_id = alias_to_book.get(normalize(parts[0]))
            try:
                chapter, verse_num = int(parts[1]), int(parts[2])
            except ValueError:
                return None
            if book_id is not None and chapter >= 1 and verse_num >= 1:
                return book_id, chapter, verse_num
    return None


# --- record parsing ------------------------------------------------------------------


def parse_ancient_record(
    record: dict[str, Any],
    lonlats: dict[str, tuple[float, float]],
    order_to_book: dict[int, str],
    alias_to_book: dict[str, str],
    ctx: str,
) -> tuple[PlaceRow | None, list[PlaceVerseRow], int]:
    """Parse one ancient place into (place row | None-if-excluded, verse links, skipped).

    Structural contract violations (missing id / friendly_id) fail loudly; individual
    unmappable verse references are skipped and counted.
    """
    place_id = record.get("id")
    friendly_id = record.get("friendly_id")
    if not isinstance(place_id, str) or not place_id:
        raise LoaderError(f"{ctx}: missing or non-string 'id'.")
    if not isinstance(friendly_id, str) or not friendly_id:
        raise LoaderError(f"{ctx}: place {place_id!r} has missing or non-string 'friendly_id'.")

    modern_associations_raw = record.get("modern_associations")
    modern_associations = (
        cast("dict[str, Any]", modern_associations_raw)
        if isinstance(modern_associations_raw, dict)
        else {}
    )
    derived = _derive(_collect_specials(record), modern_associations, lonlats)
    if derived is None:
        return None, [], 0  # excluded non-place

    url_slug = record.get("url_slug")
    article = record.get("preceding_article")
    place_row: PlaceRow = (
        place_id,
        friendly_id,
        _display_name(friendly_id),
        url_slug if isinstance(url_slug, str) else "",
        _place_type(record),
        article if isinstance(article, str) else "",
        derived.latitude,
        derived.longitude,
        derived.confidence,
        derived.confidence_score,
        derived.status,
        derived.modern_name,
    )

    verse_rows: list[PlaceVerseRow] = []
    skipped = 0
    seen: set[tuple[str, int, int]] = set()
    verses = record.get("verses")
    if isinstance(verses, list):
        for verse in cast("list[Any]", verses):
            if not isinstance(verse, dict):
                skipped += 1
                continue
            mapped = _map_verse(cast("dict[str, Any]", verse), order_to_book, alias_to_book)
            if mapped is None:
                skipped += 1
                continue
            if mapped in seen:  # a place may name the same verse twice (alternate spellings)
                continue
            seen.add(mapped)
            verse_rows.append((place_id, mapped[0], mapped[1], mapped[2]))
    return place_row, verse_rows, skipped


# --- load ----------------------------------------------------------------------------


def load_places(
    conn: sqlite3.Connection,
    geo_dir: Path,
    order_to_book: dict[int, str],
    alias_to_book: dict[str, str],
) -> GeoStats:
    """Ingest ``geo_dir/ancient.jsonl`` + ``geo_dir/modern.jsonl`` into ``places`` /
    ``place_verses``. Fails loudly if either source file is missing."""
    ancient_path = geo_dir / "ancient.jsonl"
    modern_path = geo_dir / "modern.jsonl"
    for path in (ancient_path, modern_path):
        if not path.is_file():
            raise LoaderError(f"Geography source file not found: {path}.")

    lonlats = load_modern_lonlats(modern_path)

    place_rows: list[PlaceRow] = []
    verse_rows: list[PlaceVerseRow] = []
    excluded = 0
    skipped_total = 0
    by_status: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for index, record in enumerate(_read_jsonl(ancient_path)):
        ctx = f"ancient.jsonl[{index}]"
        place_row, links, skipped = parse_ancient_record(
            record, lonlats, order_to_book, alias_to_book, ctx
        )
        skipped_total += skipped
        if place_row is None:
            excluded += 1
            continue
        if place_row[0] in seen_ids:
            raise LoaderError(f"{ctx}: duplicate place id {place_row[0]!r}.")
        seen_ids.add(place_row[0])
        place_rows.append(place_row)
        verse_rows.extend(links)  # only links for kept places (keeps the FK clean)
        by_status[place_row[10]] += 1

    conn.executemany(
        "INSERT INTO places (id, friendly_id, name, url_slug, type, preceding_article, "
        "latitude, longitude, confidence, confidence_score, status, modern_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        place_rows,
    )
    conn.executemany(
        "INSERT INTO place_verses (place_id, book_id, chapter, verse) VALUES (?, ?, ?, ?)",
        verse_rows,
    )
    return GeoStats(
        places=len(place_rows),
        place_verses=len(verse_rows),
        places_excluded=excluded,
        verse_links_skipped=skipped_total,
        by_status=dict(by_status),
    )
