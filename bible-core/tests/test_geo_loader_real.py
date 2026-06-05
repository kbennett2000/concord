"""Integration: build from the real committed OpenBible geography data and check reality.

Excluded from the default run (``-m "not integration"``); run with ``pytest -m integration``.
Pins the place count, the honesty-model exemplars (Jerusalem vs Nod/Eden), the
disambiguation foundation, and the verse round-trip against the frozen committed data.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import build_database

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parents[2]
TRANSLATIONS = REPO_ROOT / "data" / "translations"
GEOGRAPHY = REPO_ROOT / "data" / "geography"


def _build(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "bible.db"
    build_database(db, [TRANSLATIONS], None, GEOGRAPHY)
    return sqlite3.connect(db)


def test_place_count_and_status_distribution(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    assert conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] == 1340
    distribution = dict(conn.execute("SELECT status, COUNT(*) FROM places GROUP BY status"))
    assert distribution == {
        "identified": 1264,
        "disputed": 66,
        "unknown": 5,
        "symbolic": 3,
        "multiple": 2,
    }
    # every coordinate-bearing place has a confidence; every coordinate-less one does not
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM places WHERE latitude IS NOT NULL AND confidence IS NULL"
        ).fetchone()[0]
        == 0
    )
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM places WHERE latitude IS NULL AND confidence IS NOT NULL"
        ).fetchone()[0]
        == 0
    )


def test_jerusalem_is_identified(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    row = conn.execute(
        "SELECT id, latitude, longitude, confidence, status "
        "FROM places WHERE friendly_id='Jerusalem'"
    ).fetchone()
    place_id, latitude, longitude, confidence, status = row
    assert place_id == "a15257a"  # stable OpenBible id
    assert round(latitude, 3) == 31.777  # lat from lonlat parts[1]
    assert round(longitude, 3) == 35.234  # lon from lonlat parts[0] — order preserved
    assert (confidence, status) == ("high", "identified")


def test_nod_is_unknown(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    row = conn.execute(
        "SELECT id, latitude, longitude, confidence, status FROM places WHERE friendly_id='Nod'"
    ).fetchone()
    assert row == ("a1ad8e1", None, None, None, "unknown")


def test_eden_is_unknown_despite_tentative_association(tmp_path: Path) -> None:
    """The honesty model in action: the dataset marks 'Eden 1' unknown_place yet still offers
    tentative modern associations. We honor the unknown claim — null coords — rather than
    present a guess as fact. (The spec named 'Garden of Eden' as the unknown exemplar; the
    real friendly_id is 'Eden 1', slug 'eden-1', covering Gen 2:8.)"""
    conn = _build(tmp_path)
    row = conn.execute(
        "SELECT name, url_slug, latitude, longitude, status FROM places WHERE id='af3daeb'"
    ).fetchone()
    assert row == ("Eden", "eden-1", None, None, "unknown")
    # and it really is the Garden of Eden — it is linked to Genesis 2:8
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM place_verses WHERE place_id='af3daeb' AND book_id='GEN' "
            "AND chapter=2 AND verse=8"
        ).fetchone()[0]
        == 1
    )


@pytest.mark.parametrize(
    ("name", "ids"),
    [
        ("Antioch", {"ae41ab4", "a6c704a"}),
        ("Bethlehem", {"a112427", "a308715", "ab1a343"}),
    ],
)
def test_disambiguation_distinct_ids(tmp_path: Path, name: str, ids: set[str]) -> None:
    conn = _build(tmp_path)
    rows = {r[0] for r in conn.execute("SELECT id FROM places WHERE name=?", (name,))}
    assert rows == ids  # distinct places sharing a name, each its own stable id


def test_verse_round_trip(tmp_path: Path) -> None:
    conn = _build(tmp_path)
    # verse → places: Genesis 2:8 names Eden
    named = {
        r[0]
        for r in conn.execute(
            "SELECT p.friendly_id FROM place_verses pv JOIN places p ON p.id = pv.place_id "
            "WHERE pv.book_id='GEN' AND pv.chapter=2 AND pv.verse=8"
        )
    }
    assert "Eden 1" in named
    # place → verses: Jerusalem is mentioned in hundreds of verses, all in-canon
    jerusalem_refs = conn.execute(
        "SELECT COUNT(*) FROM place_verses WHERE place_id='a15257a'"
    ).fetchone()[0]
    assert jerusalem_refs > 500
    # all place_verses book ids are valid seeded books (FK + canon mapping held)
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM place_verses pv LEFT JOIN books b ON b.id = pv.book_id "
            "WHERE b.id IS NULL"
        ).fetchone()[0]
        == 0
    )
