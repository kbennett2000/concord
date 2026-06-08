"""Topical-Bible loader behaviour on synthetic fixtures: topic + verse rows land, both
directions queryable, `see_also` redirects carry zero verses, the PK dedups repeated links,
unresolved book links are skipped + counted, ordering, and idempotent rebuilds. No dependence
on the real Nave's dataset."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from bible_core.loader import build_database
from bible_core.parser import parse_reference
from bible_core.queries import (
    count_topic_verses,
    get_topic,
    get_topic_verses,
    get_topics_for_reference,
    list_topics,
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
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)], topics_dir=topics_dir)
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
        tmp_path / "bible.db", [_corpus(tmp_path)], topics_dir=tmp_path / "topics"
    )
    assert (first.topics, first.topic_verses) == (second.topics, second.topic_verses)  # type: ignore[attr-defined]


def test_no_topics_dir_yields_zero(tmp_path: Path) -> None:
    stats = build_database(tmp_path / "bible.db", [_corpus(tmp_path)])  # topics_dir omitted
    assert stats.topics == 0
    assert stats.topic_verses == 0
