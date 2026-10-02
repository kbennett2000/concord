"""Topical-Bible loader behaviour on synthetic fixtures: topic + verse rows land, both
directions queryable, `see_also` redirects carry zero verses, the PK dedups repeated links,
unresolved book links are skipped + counted, ordering, and idempotent rebuilds. ADR-0013: a
second, private directory scanned after the public one, every topic's source, the source filter
and per-source totals, and the rules that keep sources and ids apart. No dependence on the real
Nave's dataset (bar one guard over the committed ids)."""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from bible_core.loader import LoaderError, build_database
from bible_core.parser import parse_reference
from bible_core.queries import (
    count_topic_verses,
    get_topic,
    get_topic_verses,
    get_topics_for_reference,
    list_topics,
    topic_source_totals,
)
from bible_core.resolver import SqliteBookResolver
from loaderkit import book, chapter, translation, verse, write_translation


def _corpus(tmp_path: Path) -> Path:
    tdir = tmp_path / "translations"
    webx = translation(
        "WEBX",
        [
            book("Gen", 1, [chapter(1, [verse(1, "In the beginning."), verse(2, "The earth.")])]),
            book("Phil", 50, [chapter(4, [verse(6, "Be anxious for nothing.")])]),
        ],
    )
    write_translation(tdir, webx)
    return tdir


def _topics_payload() -> dict[str, object]:
    return {
        "source": "Nave's Topical Bible",
        "topics": [
            {"id": "anxiety", "name": "ANXIETY", "section": "A", "see_also": "care", "verses": []},
            {
                "id": "care",
                "name": "CARE",
                "section": "C",
                "see_also": None,
                "verses": [
                    {"book": "PHP", "chapter": 4, "verse": 6},
                    {"book": "GEN", "chapter": 1, "verse": 1},
                    {"book": "PHP", "chapter": 4, "verse": 6},  # duplicate → PK dedups
                    {"book": "ZZZ", "chapter": 1, "verse": 1},  # unresolved book → skipped
                ],
            },
            {
                "id": "creation",
                "name": "CREATION",
                "section": "C",
                "see_also": None,
                "verses": [{"book": "GEN", "chapter": 1, "verse": 1}],
            },
        ],
    }


def _build(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, object]:
    topics_dir = tmp_path / "topics"
    topics_dir.mkdir(parents=True)
    (topics_dir / "naves.json").write_text(json.dumps(payload), encoding="utf-8")
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], topics_dirs=[topics_dir])
    return tmp_path / "bible.db", stats


def test_counts_and_dedup_and_skip(tmp_path: Path) -> None:
    _, stats = _build(tmp_path, _topics_payload())
    assert stats.topics == 3  # type: ignore[attr-defined]
    # CARE: PHP 4:6 (deduped from 2) + GEN 1:1; CREATION: GEN 1:1 → 3 distinct links (ZZZ skipped).
    assert stats.topic_verses == 3  # type: ignore[attr-defined]


def test_redirect_has_see_also_and_zero_verses(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _topics_payload())
    conn = sqlite3.connect(db)
    anxiety = get_topic(conn, "anxiety")
    assert anxiety is not None
    assert anxiety.see_also == "care"
    assert count_topic_verses(conn, "anxiety") == 0


def test_topic_to_verses_ordered_and_deduped(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _topics_payload())
    conn = sqlite3.connect(db)
    rows, total = get_topic_verses(conn, "care", 50, 0)
    assert total == 2  # the duplicate PHP 4:6 collapsed; ZZZ skipped
    # Canonical order: GEN before PHP.
    assert [(r.book_id, r.chapter, r.verse) for r in rows] == [("GEN", 1, 1), ("PHP", 4, 6)]


def test_reverse_verse_to_topics(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _topics_payload())
    conn = sqlite3.connect(db)
    ref = parse_reference("Gen 1:1", SqliteBookResolver(conn))
    page = get_topics_for_reference(conn, ref)
    # Both CARE and CREATION cite GEN 1:1; ordered by name; ANXIETY (no verses) absent.
    assert [t.id for t in page.rows] == ["care", "creation"]


def test_list_filter_by_name(tmp_path: Path) -> None:
    db, _ = _build(tmp_path, _topics_payload())
    conn = sqlite3.connect(db)
    page = list_topics(conn, "anx", None, 50, 0)
    assert [t.id for t in page.rows] == ["anxiety"]
    assert page.total == 1


def test_build_is_idempotent(tmp_path: Path) -> None:
    payload = _topics_payload()
    first = _build(tmp_path, payload)[1]
    second = build_database(
        tmp_path / "bible.db", [_corpus(tmp_path)], topics_dirs=[tmp_path / "topics"]
    )
    assert (first.topics, first.topic_verses) == (second.topics, second.topic_verses)  # type: ignore[attr-defined]


def test_no_topics_dir_yields_zero(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # topics_dirs omitted
    assert stats.topics == 0
    assert stats.topic_verses == 0


# --- ADR-0013: a second source, private -----------------------------------------------

REPO_TOPICS = Path(__file__).resolve().parents[2] / "data" / "topics"
PRIVATE = "Made-up Finder"


def _private_payload() -> dict[str, object]:
    """A made-up private source: ids carry their own prefix; mixed-case names (they interleave with
    the all-capitals public names: the order ignores case)."""
    return {
        "source": PRIVATE,
        "topics": [
            {
                "id": "vf-1",
                "name": "Care made up",
                "section": "C",
                "see_also": None,
                "verses": [
                    {"book": "GEN", "chapter": 1, "verse": 1},
                    {"book": "GEN", "chapter": 1, "verse": 2},
                ],
            },
            {"id": "vf-2", "name": "Zeal made up", "section": "Z", "see_also": "vf-1"},
        ],
    }


def _write(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def _build_two(tmp_path: Path, private: dict[str, object]) -> Path:
    _write(tmp_path / "topics", "naves.json", _topics_payload())
    _write(tmp_path / "private" / "topics", "made-up.json", private)
    db = tmp_path / "bible.db"
    build_database(
        db,
        [_corpus(tmp_path)],
        topics_dirs=[tmp_path / "topics", tmp_path / "private" / "topics"],
    )
    return db


def test_two_dirs_load_both_sources(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build_two(tmp_path, _private_payload()))
    page = list_topics(conn, None, None, 50, 0)
    # name ignoring case, then id: "CARE" < "Care made up" < "CREATION" (a < r).
    assert [t.id for t in page.rows] == ["anxiety", "care", "vf-1", "creation", "vf-2"]
    assert [t.source for t in page.rows] == [
        *["Nave's Topical Bible"] * 2,
        PRIVATE,
        "Nave's Topical Bible",
        PRIVATE,
    ]
    vf2 = get_topic(conn, "vf-2")
    assert vf2 is not None and (vf2.see_also, vf2.source) == ("vf-1", PRIVATE)


def test_absent_private_dir_loads_public_only(tmp_path: Path) -> None:
    _write(tmp_path / "topics", "naves.json", _topics_payload())
    db = tmp_path / "bible.db"
    stats = build_database(
        db, [_corpus(tmp_path)], topics_dirs=[tmp_path / "topics", tmp_path / "private" / "topics"]
    )
    assert stats.topics == 3
    totals = topic_source_totals(sqlite3.connect(db), None, None)
    assert [(t.source, t.total) for t in totals] == [("Nave's Topical Bible", 3)]


def test_source_filter_and_totals(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build_two(tmp_path, _private_payload()))
    page = list_topics(conn, None, None, 50, 0, source=PRIVATE)
    assert ([t.id for t in page.rows], page.total) == (["vf-1", "vf-2"], 2)
    # Totals honour q/section, list every source (0 included), ordered by source.
    assert [(t.source, t.total) for t in topic_source_totals(conn, None, "C")] == [
        (PRIVATE, 1),
        ("Nave's Topical Bible", 2),
    ]
    assert [(t.source, t.total) for t in topic_source_totals(conn, "zzz", None)] == [
        (PRIVATE, 0),
        ("Nave's Topical Bible", 0),
    ]
    assert sum(t.total for t in topic_source_totals(conn, None, None)) == 5


def test_reverse_lookup_unions_sources(tmp_path: Path) -> None:
    conn = sqlite3.connect(_build_two(tmp_path, _private_payload()))
    page = get_topics_for_reference(conn, parse_reference("Gen 1:1", SqliteBookResolver(conn)))
    assert [(t.id, t.source) for t in page.rows] == [
        ("care", "Nave's Topical Bible"),
        ("vf-1", PRIVATE),
        ("creation", "Nave's Topical Bible"),
    ]


def test_order_ignores_case_across_sources(tmp_path: Path) -> None:
    """One A-Z list (V8-S7a): names compare ignoring case, so two sources interleave, a pair
    differing only in case keeps its alphabetical order, and names equal but for case fall back
    to id, whichever source it belongs to. The browse pages it the same way at any limit, and the
    reverse lookup uses the same order."""
    gen = [{"book": "GEN", "chapter": 1, "verse": 1}]

    def topic(tid: str, name: str) -> dict[str, object]:
        return {"id": tid, "name": name, "section": name[0].upper(), "verses": gen}

    public: dict[str, object] = {
        "source": "Made-up Index",
        "topics": [
            topic("beta-zed", "BETA (Zed)"),
            topic("beta-a-thing", "BETA (a thing)"),
            topic("cedar", "CEDAR"),
            topic("willow", "WILLOW"),
        ],
    }
    private: dict[str, object] = {
        "source": PRIVATE,
        "topics": [topic("vf-3", "cedar"), topic("vf-4", "Willow"), topic("vf-5", "Birch made up")],
    }
    _write(tmp_path / "topics", "index.json", public)
    _write(tmp_path / "private" / "topics", "made-up.json", private)
    db = tmp_path / "bible.db"
    build_database(
        db, [_corpus(tmp_path)], topics_dirs=[tmp_path / "topics", tmp_path / "private" / "topics"]
    )
    conn = sqlite3.connect(db)

    expected = ["beta-a-thing", "beta-zed", "vf-5", "cedar", "vf-3", "vf-4", "willow"]
    assert [t.id for t in list_topics(conn, None, None, 50, 0).rows] == expected
    for limit in (1, 2, 3):
        walked = [
            t.id
            for offset in range(0, len(expected), limit)
            for t in list_topics(conn, None, None, limit, offset).rows
        ]
        assert walked == expected, limit
    reverse = get_topics_for_reference(conn, parse_reference("Gen 1:1", SqliteBookResolver(conn)))
    assert [t.id for t in reverse.rows] == expected


def test_duplicate_id_across_dirs_names_both_files(tmp_path: Path) -> None:
    payload = _private_payload()
    payload["topics"] = [{"id": "care", "name": "Care made up", "section": "C"}]
    with pytest.raises(LoaderError, match=r"made-up\.json: duplicate topic id 'care'.*naves\.json"):
        _build_two(tmp_path, payload)


def test_source_in_two_files_fails(tmp_path: Path) -> None:
    payload = _private_payload()
    payload["source"] = "Nave's Topical Bible"
    with pytest.raises(LoaderError, match=r"made-up\.json: source .* already loaded from .*naves"):
        _build_two(tmp_path, payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("id", "vf/1", "lower-case letters, digits and '-'"),
        ("id", "VF-1", "lower-case letters, digits and '-'"),
        ("section", "c", "one letter A-Z"),
        ("section", "CA", "one letter A-Z"),
    ],
)
def test_bad_id_or_section_fails(tmp_path: Path, field: str, value: str, message: str) -> None:
    payload = _private_payload()
    topic = {"id": "vf-1", "name": "Care made up", "section": "C", field: value}
    payload["topics"] = [topic]
    with pytest.raises(LoaderError, match=re.escape(message)):
        _build_two(tmp_path, payload)


def test_empty_source_file_fails(tmp_path: Path) -> None:
    payload = _private_payload()
    payload["topics"] = []
    with pytest.raises(LoaderError, match="'topics' is empty"):
        _build_two(tmp_path, payload)


def test_committed_topics_keep_the_shared_rules() -> None:
    """The committed sources pass the id and section rules, and no committed id carries the
    Verse Finder's private prefix: a private build can never collide with them (ADR-0013)."""
    files = sorted(REPO_TOPICS.glob("*.json"))
    assert files, f"no committed topics under {REPO_TOPICS}"
    for path in files:
        topics = json.loads(path.read_text(encoding="utf-8"))["topics"]
        assert topics
        ids = [t["id"] for t in topics]
        assert all(re.fullmatch(r"[a-z0-9-]+", i) for i in ids), path.name
        assert all(re.fullmatch(r"[A-Z]", t["section"]) for t in topics), path.name
        assert not [i for i in ids if i.startswith("vf-")], path.name
