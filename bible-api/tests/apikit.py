"""Builds the synthetic corpus the API tests run against.

Deterministic verse text (``"JHN 3:16 (KJV)"``) lets tests assert exact strings. WEB
deliberately omits John 3:16 so the missing-verse null path is exercised (the production
corpus has it everywhere — see Slice 2/3 notes).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path

from bible_core.schema import create_schema
from bible_core.seed import seed_books

TRANSLATIONS = [
    ("KJV", "King James Version"),
    ("WEB", "World English Bible"),
    ("YLT", "Young's Literal Translation"),
]

# (translation_id, book_id, chapter, verse) tuples intentionally absent.
OMITTED = {("WEB", "JHN", 3, 16)}


def verse_text(book_id: str, chapter: int, verse: int, translation_id: str) -> str:
    return f"{book_id} {chapter}:{verse} ({translation_id})"


def build_corpus(path: Path) -> None:
    conn = sqlite3.connect(path)
    create_schema(conn)
    seed_books(conn)
    for translation_id, name in TRANSLATIONS:
        conn.execute(
            "INSERT INTO translations (id, name, language, direction, versification, attribution) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (translation_id, name, "en", "ltr", "standard", "Public domain."),
        )
    # The Greek NT, the original-language text the word-study endpoints tag (id "SBLGNT", grc). It
    # carries no synthetic verses here — the word-study endpoints read word_tokens, and the
    # /strongs/{id}/verses hydration uses an English translation — but it must be a loaded
    # translation so `?text=SBLGNT` resolves.
    conn.execute(
        "INSERT INTO translations (id, name, language, direction, versification, attribution) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("SBLGNT", "SBL Greek New Testament", "grc", "ltr", "standard", "CC BY 4.0, STEPBible."),
    )
    # The Hebrew OT, the original-language text the word-study endpoints tag for OT verses (id
    # "OSHB", grc→hbo, RTL). Like SBLGNT it carries no synthetic verses; it must be a loaded
    # translation so testament/id-based ?text= defaulting (OT → OSHB) resolves.
    conn.execute(
        "INSERT INTO translations (id, name, language, direction, versification, attribution) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("OSHB", "Open Scriptures Hebrew Bible", "hbo", "rtl", "standard", "CC BY 4.0, STEPBible."),
    )

    rows: list[tuple[str, str, int, int, str]] = []

    def add(book_id: str, chapter: int, verses: Iterable[int]) -> None:
        for translation_id, _ in TRANSLATIONS:
            for verse in verses:
                if (translation_id, book_id, chapter, verse) in OMITTED:
                    continue
                rows.append(
                    (
                        translation_id,
                        book_id,
                        chapter,
                        verse,
                        verse_text(book_id, chapter, verse, translation_id),
                    )
                )

    add("JHN", 3, range(1, 21))  # John 3:1-20 (WEB omits 3:16)
    add("JHN", 4, range(1, 11))  # John 4:1-10
    add("GEN", 1, range(1, 4))  # Genesis 1:1-3
    add("1JN", 1, range(1, 4))  # 1 John 1:1-3

    conn.executemany(
        "INSERT INTO verses (translation_id, book_id, chapter, verse, text) VALUES (?, ?, ?, ?, ?)",
        rows,
    )
    conn.execute("INSERT INTO verses_fts(verses_fts) VALUES('rebuild')")

    # Compute chapter_count for populated books, mirroring the loader, so /books returns
    # real values (books without verses keep the seeded NULL).
    conn.execute(
        "UPDATE books SET chapter_count = ("
        "  SELECT COUNT(DISTINCT v.chapter) FROM verses v WHERE v.book_id = books.id"
        ") WHERE id IN (SELECT DISTINCT book_id FROM verses)"
    )

    # Deterministic cross-references for the endpoint tests:
    #  - John 3:16 → 4 targets (votes 50/40/30/5) incl. a same-chapter range (JHN 4:2-4)
    #  - John 4:1  → JHN 3:16, which WEB omits (exercises include_text null)
    # (from_book, from_ch, from_v, to_book, to_ch, to_vstart, to_vend, votes)
    cross_refs = [
        ("JHN", 3, 16, "GEN", 1, 1, None, 50),
        ("JHN", 3, 16, "1JN", 1, 1, None, 40),
        ("JHN", 3, 16, "JHN", 4, 2, 4, 30),  # same-chapter range target
        ("JHN", 3, 16, "JHN", 4, 1, None, 5),  # low votes (min_votes filter)
        ("JHN", 4, 1, "JHN", 3, 16, None, 20),  # target WEB omits
    ]
    conn.executemany(
        "INSERT INTO cross_references "
        "(from_book_id, from_chapter, from_verse, to_book_id, to_chapter, "
        "to_verse_start, to_verse_end, votes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        cross_refs,
    )

    # Deterministic geography for the places endpoints:
    #  - Jerusalem: identified, coords (named lat/lon), linked to JHN 3:16 + GEN 1:1-2
    #  - Nod: unknown, NULL coords/confidence (the honesty model)
    #  - two Antiochs sharing name "Antioch": disambiguation, one disputed
    # (id, friendly_id, name, url_slug, type, article, lat, lon, conf, score, status, modern)
    places = [
        (
            "p_jeru",
            "Jerusalem",
            "Jerusalem",
            "jerusalem",
            "settlement",
            "",
            31.78,
            35.23,
            "high",
            1000,
            "identified",
            "Jerusalem",
        ),
        ("p_nod", "Nod", "Nod", "nod", "region", "", None, None, None, None, "unknown", None),
        (
            "p_ant1",
            "Antioch 1",
            "Antioch",
            "antioch-1",
            "settlement",
            "",
            36.20,
            36.16,
            "high",
            900,
            "identified",
            "Antakya",
        ),
        (
            "p_ant2",
            "Antioch 2",
            "Antioch",
            "antioch-2",
            "settlement",
            "",
            38.30,
            31.18,
            "medium",
            300,
            "disputed",
            "Yalvaç",
        ),
    ]
    place_verses = [
        ("p_jeru", "JHN", 3, 16),  # WEB omits this verse → include_text null path
        ("p_jeru", "GEN", 1, 1),
        ("p_jeru", "GEN", 1, 2),
        ("p_nod", "JHN", 4, 1),
        ("p_ant1", "1JN", 1, 1),
        ("p_ant2", "1JN", 1, 2),
    ]
    conn.executemany(
        "INSERT INTO places (id, friendly_id, name, url_slug, type, preceding_article, "
        "latitude, longitude, confidence, confidence_score, status, modern_name) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        places,
    )
    conn.executemany(
        "INSERT INTO place_verses (place_id, book_id, chapter, verse) VALUES (?, ?, ?, ?)",
        place_verses,
    )

    # Deterministic journeys (v7) over the existing places, for the journeys endpoints:
    #  - j_paul: ordered stops with REVISITS (p_jeru at 1 & 4, p_ant1 at 2 & 3) → reverse dedup;
    #    leaves p_ant2 in NO journey → the reverse-empty (200) case
    #  - j_wander: a single stop on p_nod (unknown place) → null-coord stop path; null dating
    # Ordered by id: j_paul before j_wander.
    # (id, name, scripture, dating, source, note)
    journeys = [
        (
            "j_paul",
            "Paul Test Journey",
            "Acts 13-14",
            "c. AD 47 (test)",
            "Acts (test).",
            "One proposed reconstruction (test).",
        ),
        (
            "j_wander",
            "Wander Test",
            "Genesis 4",
            None,
            "Genesis (test).",
            "One reconstruction (test).",
        ),
    ]
    # (journey_id, ordinal, place_id, reference)
    journey_stops = [
        ("j_paul", 1, "p_jeru", "Acts 13:1"),
        ("j_paul", 2, "p_ant1", "Acts 13:14"),
        ("j_paul", 3, "p_ant1", "Acts 14:21"),  # revisit p_ant1
        ("j_paul", 4, "p_jeru", "Acts 14:26"),  # return to p_jeru
        ("j_wander", 1, "p_nod", "Genesis 4:16"),  # unknown place → null coords
    ]
    conn.executemany(
        "INSERT INTO journeys (id, name, scripture, dating, source, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        journeys,
    )
    conn.executemany(
        "INSERT INTO journey_stops (journey_id, ordinal, place_id, reference) VALUES (?, ?, ?, ?)",
        journey_stops,
    )

    # Deterministic translator's notes (v4) for the notes endpoint tests. KJV has notes; WEB has
    # none (so a loaded translation with zero notes returns 200 empty — the public-image case).
    #  - KJV JHN 3:16 → two notes (ordinals 1,2; a tn with two cross-refs + a sn)
    #  - KJV JHN 3:17 → one tc note
    #  - KJV GEN 1:1  → one plain note (NULL type)
    # Notes 5–6 are a v5 notes-search fixture: an identical body in two books (GEN before 1JN
    # canonically) so a query ties on FTS rank and the canonical tiebreak is observable. They sit
    # in chapters no notes-endpoint chapter-read asserts on (GEN 2, 1JN 1), keeping v4 tests intact.
    # (id, translation_id, book_id, chapter, verse, note_type, text, char_offset, marker, ordinal)
    notes = [
        (1, "KJV", "JHN", 3, 16, "tn", "On the Greek behind 'so loved'.", 8, "1", 1),
        (2, "KJV", "JHN", 3, 16, "sn", "A study note on divine love.", 20, "2", 2),
        (3, "KJV", "JHN", 3, 17, "tc", "A text-critical variant note.", 0, None, 1),
        (4, "KJV", "GEN", 1, 1, None, "A plain footnote with no type.", 3, None, 1),
        (5, "KJV", "GEN", 2, 1, "tn", "A tiebreak fixture note.", 0, None, 1),
        (6, "KJV", "1JN", 1, 1, "tn", "A tiebreak fixture note.", 0, None, 1),
    ]
    # (note_id, to_book_id, to_chapter, to_verse_start, to_verse_end)
    note_cross_refs = [
        (1, "GEN", 1, 1, None),  # single-verse target
        (1, "JHN", 4, 2, 4),  # same-chapter range target
    ]
    conn.executemany(
        "INSERT INTO translator_notes "
        "(id, translation_id, book_id, chapter, verse, note_type, text, char_offset, "
        "marker, ordinal) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        notes,
    )
    conn.executemany(
        "INSERT INTO note_cross_references "
        "(note_id, to_book_id, to_chapter, to_verse_start, to_verse_end) VALUES (?, ?, ?, ?, ?)",
        note_cross_refs,
    )
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES('rebuild')")

    # Deterministic section headings for the headings endpoint tests. WEB carries headings on
    # JHN 3 (two, to prove order); KJV carries one on GEN 1; YLT carries NONE (the empty-on-stock
    # case, like the real BSB). before_verse anchors the heading; ordinal is source array order.
    # (translation_id, book_id, chapter, before_verse, text, ordinal)
    headings = [
        ("WEB", "JHN", 3, 1, "Jesus Teaches Nicodemus", 1),
        ("WEB", "JHN", 3, 16, "God's Love", 2),
        ("KJV", "GEN", 1, 1, "The Creation", 1),
    ]
    conn.executemany(
        "INSERT INTO section_headings "
        "(translation_id, book_id, chapter, before_verse, text, ordinal) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        headings,
    )

    # Deterministic topical Bible (Nave's pattern) for the topics endpoint tests:
    #  - ANXIETY → a "See CARE" redirect: see_also='care', zero verses (the redirect case)
    #  - CARE → GEN 1:1, JHN 3:16 (WEB omits → include_text null path), 1JN 1:1
    #  - CREATION → GEN 1:1, GEN 1:2
    #  - LOVE → JHN 3:16  (so JHN 3:16 reverse-maps to CARE + LOVE, ordered by name)
    # (id, name, section, see_also, source)
    topics = [
        ("anxiety", "ANXIETY", "A", "care", "Nave's Topical Bible"),
        ("care", "CARE", "C", None, "Nave's Topical Bible"),
        ("creation", "CREATION", "C", None, "Nave's Topical Bible"),
        ("love", "LOVE", "L", None, "Nave's Topical Bible"),
    ]
    topic_verses = [
        ("care", "GEN", 1, 1),
        ("care", "JHN", 3, 16),  # WEB omits this verse → include_text null path
        ("care", "1JN", 1, 1),
        ("creation", "GEN", 1, 1),
        ("creation", "GEN", 1, 2),
        ("love", "JHN", 3, 16),
    ]
    conn.executemany(
        "INSERT INTO topics (id, name, section, see_also, source) VALUES (?, ?, ?, ?, ?)",
        topics,
    )
    conn.executemany(
        "INSERT INTO topic_verses (topic_id, book_id, chapter, verse) VALUES (?, ?, ?, ?)",
        topic_verses,
    )

    # Deterministic Strong's lexicon for the /v1/strongs endpoint tests:
    #  - G25 ἀγαπάω / G26 ἀγάπη — two Greek "love" words (browse 'love' / numeric order)
    #  - H430 אֱלֹהִים — a Hebrew entry (language filter)
    # (strongs_id, language, lemma, transliteration, gloss, definition, source)
    strongs_entries = [
        ("G26", "grc", "ἀγάπη", "agapē", "love", "love, goodwill, esteem.", "STEP Bible"),
        ("G25", "grc", "ἀγαπάω", "agapaō", "to love", "to love, to esteem.", "STEP Bible"),
        ("H430", "hbo", "אֱלֹהִים", "ʾelōhîm", "God", "God, gods, rulers.", "STEP Bible"),
    ]
    conn.executemany(
        "INSERT INTO strongs_entries "
        "(strongs_id, language, lemma, transliteration, gloss, definition, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        strongs_entries,
    )

    # Deterministic SBLGNT word tokens for the /strongs/{id}/verses + /verses/{ref}/words tests:
    #  - JHN 3:16: G9999 (no lexicon entry → null lemma join), G25 (joins ἀγαπάω), and an untagged
    #    word (null strongs/morph) — exercises ordering + the lexicon LEFT JOIN.
    #  - G26 in JHN 4:7 and 4:8 → two distinct verses for the Strong's→verses concordance (KJV has
    #    those verses, so include_text hydrates; ?translation=WEB on JHN 3:16 → text null).
    # (text_id, book_id, chapter, verse, position, surface_form, strongs_id, morph_code)
    word_tokens = [
        ("SBLGNT", "JHN", 3, 16, 1, "θεὸς", "G9999", "N-NSM"),
        ("SBLGNT", "JHN", 3, 16, 2, "ἠγάπησεν", "G25", "V-AAI-3S"),
        ("SBLGNT", "JHN", 3, 16, 3, "γὰρ", None, None),
        ("SBLGNT", "JHN", 4, 7, 1, "ἀγάπη", "G26", "N-NSF"),
        ("SBLGNT", "JHN", 4, 8, 1, "ἀγάπη", "G26", "N-NSF"),
        # Hebrew tokens (text_id OSHB) for the OT word-study path — H430 (אֱלֹהִים) joins the H430
        # lexicon entry seeded above and occurs in GEN 1:1 + 1:2 (the Strong's→verses direction).
        ("OSHB", "GEN", 1, 1, 1, "בְּרֵאשִׁית", "H7225", "Ncfsa"),
        ("OSHB", "GEN", 1, 1, 3, "אֱלֹהִים", "H430", "Ncmpa"),
        ("OSHB", "GEN", 1, 2, 1, "אֱלֹהִים", "H430", "Ncmpa"),
    ]
    conn.executemany(
        "INSERT INTO word_tokens "
        "(text_id, book_id, chapter, verse, position, surface_form, strongs_id, morph_code) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        word_tokens,
    )

    conn.commit()
    conn.close()
