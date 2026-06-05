"""Geography load: the honesty model, disambiguation, stable ids, verse round-trips.

Synthetic fixtures (no dependence on the real 14 MB files). The real-data assertions
(Jerusalem, Nod, Eden, place count) live in test_geo_loader_real.py (integration).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from geokit import ancient_place, assoc, modern_loc, osis_only_verse, verse_ref, write_geo
from loaderkit import book, chapter, translation, verse, write_translation

# Modern locations referenced by the place fixtures (id → lon, lat).
MODERN = [
    modern_loc("m_jeru", 35.234167, 31.776667),  # Jerusalem
    modern_loc("m_ant1", 36.226691, 36.20),  # Antioch on the Orontes
    modern_loc("m_ant2", 38.306111, 38.30),  # Antioch of Pisidia
    modern_loc("m_neg", 35.13, 31.72),  # the net-negative identification
    modern_loc("m_ches", 35.01, 31.79),  # Chesalon (recursive + strong score)
    modern_loc("m_eden", 44.0, 33.0),  # Eden's tentative association
    modern_loc("m_zap", 35.9, 32.6),  # Zaphon (nonspecific + strong score)
    modern_loc("m_comp_a", 35.0, 32.0),
    modern_loc("m_comp_b", 35.1, 32.1),
    modern_loc("m_osis", 34.0, 31.0),
]

# A representative fixture exercising every status path and edge.
ANCIENT = [
    # identified, high confidence; verse link Gen 2:8 (for the round-trip)
    ancient_place(
        "a15257a",
        "Jerusalem",
        associations={"m_jeru": assoc(1000, "Jerusalem")},
        verses=[verse_ref(1, 2, 8)],
    ),
    # unknown — special, no association, no coordinates (honesty model); Gen 4:16
    ancient_place("a_nod", "Nod", specials=("unknown_place",), verses=[verse_ref(1, 4, 16)]),
    # Eden: a semantic special WINS over a tentative association → unknown, null coords; Gen 2:8
    ancient_place(
        "a_eden",
        "Eden 1",
        specials=("unknown_place",),
        associations={"m_eden": assoc(178, "tentative")},
        verses=[verse_ref(1, 2, 8)],
    ),
    # disambiguation: two Antiochs → distinct rows, distinct ids, both named "Antioch"
    ancient_place("a_ant1", "Antioch 1", associations={"m_ant1": assoc(900, "Antakya")}),
    ancient_place("a_ant2", "Antioch 2", associations={"m_ant2": assoc(700, "Yalvaç")}),
    # net-negative best score → disputed (NOT identified), coords kept, confidence low
    ancient_place("a_neg", "Bether", associations={"m_neg": assoc(-87, "Battir")}),
    # recursive is a path artifact, not a semantic claim → does NOT void a strong association
    ancient_place(
        "a_ches",
        "Chesalon",
        specials=("recursive",),
        associations={"m_ches": assoc(702, "Kesla")},
    ),
    # recursive-only, no association → honestly unknown
    ancient_place("a_rec", "Lostloop", specials=("recursive",)),
    # nonspecific semantic special wins over a strong association → symbolic, null coords
    ancient_place(
        "a_zap",
        "Zaphon 2",
        specials=("nonspecific_place",),
        associations={"m_zap": assoc(1041, "Jebel Aqra")},
    ),
    # multiple_locations special → multiple, null coords
    ancient_place("a_holy", "Holy Place 1", specials=("multiple_locations",)),
    # competing near-tie associations → disputed, coords present
    ancient_place(
        "a_comp",
        "Aenon",
        associations={"m_comp_a": assoc(276, "A"), "m_comp_b": assoc(255, "B")},
    ),
    # osis-only verse (no sort) exercises the fallback; out-of-canon sort is skipped
    ancient_place(
        "a_osis",
        "Osisville",
        associations={"m_osis": assoc(600, "Moderntown")},
        verses=[osis_only_verse("Gen.1.1"), verse_ref(70, 1, 1)],  # book 70 is out of canon
    ),
    # purely not_a_place, no association → EXCLUDED entirely
    ancient_place("a_nap", "Notaplace", specials=("not_a_place",)),
]

KEPT = len(ANCIENT) - 1  # everything but the excluded not_a_place


def _corpus(tmp_path: Path) -> Path:
    """A tiny translation so the build has verses; books are seeded regardless."""
    tdir = tmp_path / "translations"
    write_translation(tdir, translation("KJVX", [book("Gen", 1, [chapter(1, [verse(1, "x")])])]))
    return tdir


def _build(tmp_path: Path, db_name: str = "bible.db") -> Path:
    db = tmp_path / db_name
    geo_dir = write_geo(tmp_path / "geo", ANCIENT, MODERN)
    build_database(db, [_corpus(tmp_path)], None, geo_dir)
    return db


def test_place_count_and_idempotent(tmp_path: Path) -> None:
    a = _build(tmp_path, "a.db")
    b = _build(tmp_path, "b.db")
    conn = sqlite3.connect(a)
    assert conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] == KEPT
    # byte-identical rebuild
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


def test_identified_place_has_coords_and_high_confidence(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT id, name, latitude, longitude, confidence, confidence_score, status, modern_name "
        "FROM places WHERE friendly_id='Jerusalem'"
    ).fetchone()
    assert row == (
        "a15257a",
        "Jerusalem",
        31.776667,
        35.234167,
        "high",
        1000,
        "identified",
        "Jerusalem",
    )


def test_unknown_place_has_null_coords(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT latitude, longitude, confidence, confidence_score, status "
        "FROM places WHERE friendly_id='Nod'"
    ).fetchone()
    assert row == (None, None, None, None, "unknown")


def test_semantic_special_overrides_association(tmp_path: Path) -> None:
    """Eden carries a tentative association but an unknown_place special → unknown, no coords."""
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT name, latitude, longitude, status FROM places WHERE friendly_id='Eden 1'"
    ).fetchone()
    assert row == ("Eden", None, None, "unknown")


def test_disambiguation_distinct_ids(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    rows = conn.execute("SELECT id FROM places WHERE name='Antioch' ORDER BY id").fetchall()
    ids = [r[0] for r in rows]
    assert ids == ["a_ant1", "a_ant2"]  # two distinct rows, two distinct ids


def test_stable_ids_are_openbible_ids(tmp_path: Path) -> None:
    """places.id is the OpenBible 'a…' id from the source, never a row position."""
    conn = sqlite3.connect(_build(tmp_path))
    ids = {r[0] for r in conn.execute("SELECT id FROM places")}
    assert "a15257a" in ids and "a_nod" in ids
    assert all(isinstance(i, str) and i.startswith("a") for i in ids)


def test_recursive_does_not_void_strong_association(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT latitude, confidence, status FROM places WHERE friendly_id='Chesalon'"
    ).fetchone()
    assert row == (31.79, "high", "identified")


def test_recursive_only_is_unknown(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT latitude, status FROM places WHERE friendly_id='Lostloop'"
    ).fetchone()
    assert row == (None, "unknown")


def test_negative_score_is_disputed_not_identified(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT latitude, longitude, confidence, status FROM places WHERE friendly_id='Bether'"
    ).fetchone()
    assert row == (31.72, 35.13, "low", "disputed")  # coords kept, hedged — never 'identified'


def test_competing_associations_are_disputed(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    status = conn.execute("SELECT status FROM places WHERE friendly_id='Aenon'").fetchone()[0]
    assert status == "disputed"


@pytest.mark.parametrize(
    ("friendly_id", "status"),
    [("Zaphon 2", "symbolic"), ("Holy Place 1", "multiple")],
)
def test_special_statuses_have_null_coords(tmp_path: Path, friendly_id: str, status: str) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    row = conn.execute(
        "SELECT latitude, longitude, status FROM places WHERE friendly_id=?", (friendly_id,)
    ).fetchone()
    assert row == (None, None, status)


def test_excluded_not_a_place(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    assert (
        conn.execute("SELECT COUNT(*) FROM places WHERE friendly_id='Notaplace'").fetchone()[0] == 0
    )


def test_verse_link_round_trip(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    # place → verses
    refs = conn.execute(
        "SELECT book_id, chapter, verse FROM place_verses WHERE place_id='a15257a'"
    ).fetchall()
    assert refs == [("GEN", 2, 8)]
    # verse → places: Gen 2:8 is named by both Jerusalem and Eden (fixture)
    names = {
        r[0]
        for r in conn.execute(
            "SELECT p.friendly_id FROM place_verses pv JOIN places p ON p.id = pv.place_id "
            "WHERE pv.book_id='GEN' AND pv.chapter=2 AND pv.verse=8"
        )
    }
    assert names == {"Jerusalem", "Eden 1"}


def test_osis_fallback_and_out_of_canon_skip(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build(tmp_path))
    # the osis-only verse mapped to Gen 1:1; the out-of-canon (book 70) ref was skipped
    refs = conn.execute(
        "SELECT book_id, chapter, verse FROM place_verses WHERE place_id='a_osis'"
    ).fetchall()
    assert refs == [("GEN", 1, 1)]


def test_missing_source_files_raise(tmp_path: Path) -> None:
    geo_dir = tmp_path / "geo_empty"
    geo_dir.mkdir()
    (geo_dir / "ancient.jsonl").write_text("", encoding="utf-8")  # modern.jsonl missing
    with pytest.raises(LoaderError, match="Geography source file not found"):
        build_database(tmp_path / "bible.db", [_corpus(tmp_path)], None, geo_dir)


def test_malformed_jsonl_raises(tmp_path: Path) -> None:
    geo_dir = tmp_path / "geo_bad"
    geo_dir.mkdir()
    (geo_dir / "ancient.jsonl").write_text("{not valid json}\n", encoding="utf-8")
    (geo_dir / "modern.jsonl").write_text("", encoding="utf-8")
    with pytest.raises(LoaderError, match="invalid JSON"):
        build_database(tmp_path / "bible.db", [_corpus(tmp_path)], None, geo_dir)
