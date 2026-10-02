"""The Verse Finder on synthetic pdftohtml XML (V8-S6b; made-up text only): the index paired
with the topics, a topic's head, pointer and entries, references of every shape expanded to
their verses, the topics payload and the document, the loaders' own checks on both, the
failures that block the write, and the EPUB witness's keys."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from bible_core.documents import parse_documents_file
from bible_core.normalize import normalize
from bible_core.seed import load_canonical_books_text, parse_canonical_books
from bible_core.topics import parse_topics_file
from emb_convert.clean import Fixes, PublicWords
from emb_convert.documents import find_front
from emb_convert.layout import find_layout
from emb_convert.notes import context
from emb_convert.pdfxml import parse_pdf_xml
from emb_convert.skeleton import load_skeleton
from emb_convert.text import parse_bible
from emb_convert.versefinder import FinderFindings, build_finder, key
from pdfxmlkit import T, body, document, header, start, vnum

GEN = start("GEN") + 1
EXO = start("EXO") + 1
COPY, FINDER, PLAN = 4, 20, 40
ALPHA, BETA, GAMMA, DELTA = FINDER + 1, FINDER + 2, FINDER + 3, FINDER + 4
OUTLINE = [(FINDER, "A Made-up Finder"), (PLAN, "A Made-up Plan")]

Pages = dict[int, list[T]]


def chapter(code: str, number: int, count: int) -> list[T]:
    """A chapter's page: its header and ``count`` made-up verses, close together."""
    items = header(code, number)
    for n in range(1, count + 1):
        items += [vnum(str(n), 70 + 13 * n), body(f"Verse {n}.", 70 + 13 * n, 45)]
    return items


# GEN 1 and EXO 1 printed whole; GEN 2 only to verse 3 (its 4th verse stands for one the NLT
# omits: the skeleton has it, the text doesn't)
BIBLE: Pages = {
    GEN: chapter("GEN", 1, 31),
    GEN + 1: chapter("GEN", 2, 3),
    EXO: chapter("EXO", 1, 22),
}


def entry(top: int, words: str, reference: str, page: int) -> list[T]:
    """An entry on one line: the statement, "(", the linked reference, ")"."""
    return [
        T(f"{words} (", top, 46, width=8 * len(words) // 2),
        T(reference, top, 200, blue=True, link=page, width=60),
        T(")", top, 262, width=4),
    ]


def head(name: str, top: int = 54, pointer: Sequence[tuple[str, int | None]] = ()) -> list[T]:
    """A topic's name in bold; a pointer's words in bold italic, each target a link."""
    items = [T(name, top, 38, bold=True, width=60)]
    if pointer:
        items.append(T("(see ", top, 100, bold=True, italic=True, width=20))
        for n, (words, page) in enumerate(pointer):
            if n:
                items.append(T(", ", top, 120 + 60 * n - 4, bold=True, italic=True, width=4))
            items.append(
                T(words, top, 120 + 60 * n, blue=True, bold=True, italic=True, link=page, width=50)
            )
        items.append(T(")", top, 300, bold=True, italic=True, width=4))
    return items


def finder_pages() -> Pages:
    return {
        COPY: [T("A made-up book copyright © 2000 by Nobody. All rights reserved.", 54, 38, 9)],
        FINDER: [
            T("A MADE-UP FINDER", 54, 72, 15, bold=True),
            *(
                T(name, 72 + 14 * n, 38, blue=True, link=page, width=60)
                for n, (name, page) in enumerate(
                    [("Alpha Topic", ALPHA), ("Beta Topic", BETA), ("Gamma Topic", GAMMA)]
                    + [("Delta Topic", DELTA)]
                )
            ),
        ],
        ALPHA: [
            *head("Alpha Topic"),
            *entry(68, "A made-up statement", "Genesis 1:2", GEN),
            # a statement that wraps, its reference cut by the wrap ("Genesis" / "1:30–2:2")
            T("A longer made-up statement that runs on to the margin (", 83, 46, width=270),
            T("Genesis", 83, 316, blue=True, link=GEN, width=30),
            T("1:30–2:2", 97, 38, blue=True, link=GEN, width=40),
            T(")", 97, 78, width=4),
        ],
        BETA: [
            *head("Beta Topic", pointer=[("Alpha Topic", ALPHA)]),
            *entry(68, "A whole made-up chapter", "Exodus 1", EXO),
            *entry(83, "Two made-up verses", "Genesis 1:3, 5", GEN),
        ],
        GAMMA: [*head("Gamma Topic", pointer=[("Alpha Topic", ALPHA), ("Beta-Topic", BETA)])],
        DELTA: [
            *head("Delta Topic"),
            *entry(68, "A range over a verse the text lacks", "Genesis 2:2-4", GEN + 1),
            *entry(83, "A verse cited again", "Genesis 2:3", GEN + 1),
        ],
    }


def finder(pages: Mapping[int, Sequence[T]] | None = None) -> FinderFindings:
    given = {**BIBLE, **finder_pages()} if pages is None else dict(pages)
    doc = parse_pdf_xml(document(given, OUTLINE))
    layout = find_layout(doc)
    words = PublicWords(())
    result = parse_bible(doc, layout, Fixes(), words)
    ctx = context(doc, layout, result, words, load_skeleton())
    return build_finder(find_front(doc, layout).references, ctx)


def payload_topics(found: FinderFindings) -> list[dict[str, Any]]:
    assert found.payload is not None
    return list(found.payload["topics"])  # type: ignore[arg-type]


# --- reading -------------------------------------------------------------------------------------


def test_topics_pair_with_the_index_and_read_their_forms() -> None:
    found = finder()
    assert found.ok, (found.errors, found.hygiene)
    assert (found.pages, len(found.index), len(found.topics)) == (PLAN - FINDER, 4, 4)
    assert [t.name for t in found.topics] == [
        "Alpha Topic",
        "Beta Topic",
        "Gamma Topic",
        "Delta Topic",
    ]
    assert (found.entries, found.references, found.other_lines) == (6, 6, 0)
    assert [t.number for t in found.redirects] == [3]
    assert [t.number for t in found.see_also] == [2]
    # the hyphenated pointer names topic 2 by its page and letters
    assert [t.targets for t in found.topics] == [[], [1], [1, 2], []]


def test_references_of_every_shape_expand_to_their_verses() -> None:
    found = finder()
    assert found.shapes == Counter(
        {"a verse": 4, "verses in one chapter": 1, "across chapters": 1, "a whole chapter": 1}
    )
    assert found.lists == 1
    verses = {t["id"]: [(v["book"], v["chapter"], v["verse"]) for v in t["verses"]]
              for t in payload_topics(found)}  # fmt: skip
    assert verses["vf-1"] == [("GEN", 1, 2), ("GEN", 1, 30), ("GEN", 1, 31), ("GEN", 2, 1),
                              ("GEN", 2, 2)]  # fmt: skip
    assert verses["vf-2"] == [*(("EXO", 1, v) for v in range(1, 23)), ("GEN", 1, 3), ("GEN", 1, 5)]
    assert verses["vf-3"] == []
    # a verse the text lacks is skipped and listed; one cited twice is kept once
    assert verses["vf-4"] == [("GEN", 2, 2), ("GEN", 2, 3)]
    assert found.omitted == ["VF topic 4 → GEN.2.2-4 (GEN 2:4)"]
    assert (found.repeats, found.links) == (1, 31)
    assert found.evidence == Counter({"agrees": 6})


def test_the_payload_is_the_topics_contract() -> None:
    topics = payload_topics(finder())
    assert [(t["id"], t["name"], t["section"], t["see_also"]) for t in topics] == [
        ("vf-1", "Alpha Topic", "A", None),
        ("vf-2", "Beta Topic", "B", None),  # "see also": not a redirect
        ("vf-3", "Gamma Topic", "G", "vf-1"),  # "see": its first target
        ("vf-4", "Delta Topic", "D", None),
    ]


def test_the_document_prints_each_topic_as_the_book_does() -> None:
    found = finder()
    assert found.document is not None
    assert {k: v for k, v in found.document.items() if k != "text"} == {
        "slug": "front-matter-6",
        "kind": "front-matter",
        "title": "A Made-up Finder",
        "ordinal": 6,
    }
    assert str(found.document["text"]).split("\n\n") == [
        "## Alpha Topic",
        "- A made-up statement ([Genesis 1:2](ref:GEN.1.2))\n"
        "- A longer made-up statement that runs on to the margin "
        "([Genesis 1:30–2:2](ref:GEN.1.30-2.2))",
        "## Beta Topic",
        "(*see Alpha Topic*)",
        "- A whole made-up chapter ([Exodus 1](ref:EXO.1))\n"
        "- Two made-up verses ([Genesis 1:3](ref:GEN.1.3), [5](ref:GEN.1.5))",
        "## Gamma Topic",
        "(*see Alpha Topic, Beta-Topic*)",
        "## Delta Topic",
        "- A range over a verse the text lacks ([Genesis 2:2-4](ref:GEN.2.2-4))\n"
        "- A verse cited again ([Genesis 2:3](ref:GEN.2.3))",
    ]


def test_both_outputs_pass_their_loaders(tmp_path: Path) -> None:
    found = finder()
    seeds = parse_canonical_books(load_canonical_books_text())
    aliases = {normalize(alias): s.id for s in seeds for alias in s.aliases}
    topics_file = tmp_path / "topics.json"
    topics_file.write_text(json.dumps(found.payload), encoding="utf-8")
    topics, links = parse_topics_file(topics_file, aliases, Counter())
    assert [(t[0], t[4]) for t in topics][:1] == [("vf-1", "Tyndale Verse Finder")]
    assert len({link[1:] + (link[0],) for link in links}) == 31
    documents_file = tmp_path / "documents.json"
    documents_file.write_text(
        json.dumps({"translation": "EMB", "documents": [found.document]}), encoding="utf-8"
    )
    _, rows, _ = parse_documents_file(
        documents_file, 1, frozenset({"EMB"}), aliases, {"EMB": frozenset()}
    )
    assert [row[2] for row in rows] == ["front-matter-6"]


def test_each_topic_is_witnessed_by_its_number() -> None:
    found = finder()
    assert found.witnessed.order == [key(n) for n in range(1, 5)]
    assert found.witnessed.openings[key(1)] == "Alpha Topic A made-up statement"


# --- what blocks the write -----------------------------------------------------------------------


def test_an_index_link_to_no_topic_blocks_the_write() -> None:
    pages = {**BIBLE, **finder_pages()}
    pages[FINDER] = [*pages[FINDER], T("Epsilon Topic", 128, 38, blue=True, link=FINDER + 9)]
    found = finder(pages)
    assert any("doesn't pair" in e for e in found.errors)
    assert not found.ok


def test_a_pointer_to_no_topic_blocks_the_write() -> None:
    pages = {**BIBLE, **finder_pages()}
    pages[GAMMA] = head("Gamma Topic", pointer=[("Alpha Topic", FINDER + 9)])
    found = finder(pages)
    assert found.errors == [f"VF topic 3: a pointer to no topic (p{FINDER + 9})"]
    assert not found.ok


def test_a_pointer_whose_words_name_another_topic_blocks_the_write() -> None:
    pages = {**BIBLE, **finder_pages()}
    pages[GAMMA] = head("Gamma Topic", pointer=[("Delta Topic", ALPHA)])
    assert finder(pages).errors == ["VF topic 3: a pointer's words aren't topic 1's"]


def test_an_unreadable_reference_blocks_the_write() -> None:
    pages = {**BIBLE, **finder_pages()}
    pages[DELTA] = [*head("Delta Topic"), *entry(68, "A made-up statement", "Nowhere 1:1", GEN)]
    found = finder(pages)
    assert [e for e in found.errors if "Nowhere" in e]
    assert not found.ok


def test_a_line_of_no_known_form_blocks_the_write() -> None:
    pages = {**BIBLE, **finder_pages()}
    pages[DELTA] = [*head("Delta Topic"), T("A made-up subhead", 68, 38, italic=True, width=80)]
    found = finder(pages)
    assert found.other_lines == 1
    assert not found.ok
