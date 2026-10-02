"""The broken- and glued-word repair (scripts/fix_broken_words.py), on made-up text only.

Each corpus is two or three made-up "translations" that share a filler of plain sentences (so
the common words have counts) and differ in one test verse.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from fix_broken_words import (
    Corpus,
    Findings,
    Ref,
    apply_changes,
    detect,
    main,
    quick_check,
    repair,
)

FILLER = (
    "and the man said that he would go with them",
    "the word shall be with him and with his house",
    "then he saw both of them in the field",
    "they dwell in the house of the man",
)
TEST: Ref = (1, 2, 1)
Texts = dict[str, dict[Ref, str]]


def corpus(verses: Mapping[str, str], extra: Mapping[str, Sequence[str]] | None = None) -> Texts:
    """One made-up translation per entry of ``verses``: filler, its extra lines, its test verse."""
    texts: Texts = {}
    for code, verse in verses.items():
        lines = {(1, 1, n + 1): FILLER[n % len(FILLER)] for n in range(20 * len(FILLER))}
        for n, line in enumerate((extra or {}).get(code, ())):
            lines[(1, 3, n + 1)] = line
        lines[TEST] = verse
        texts[code] = lines
    return texts


def both(lines: Sequence[str], codes: Sequence[str] = ("AAA", "BBB")) -> dict[str, Sequence[str]]:
    return {code: lines for code in codes}


def find(texts: Texts) -> Findings:
    return detect(Corpus(texts))


def fixed(texts: Texts, code: str = "AAA") -> str:
    repair(texts)
    return texts[code][TEST]


# -- words split by a stray space ----------------------------------------------------------


def test_a_first_letter_split_off_is_joined() -> None:
    texts = corpus({"AAA": "they went in t he field", "BBB": "they went in the field"})
    found = find(texts)
    assert [(c.code, c.kind, c.before, c.after) for c in found.changes] == [
        ("AAA", "split", "in t he field", "in the field")
    ]
    assert fixed(texts) == "they went in the field"


def test_a_last_letter_split_off_is_joined() -> None:
    texts = corpus({"AAA": "the man an d the field", "BBB": "the man and the field"})
    assert fixed(texts) == "the man and the field"


def test_a_word_split_inside_is_joined() -> None:
    extra = both(["the plovish was in the field", "a plovish was in the house"])
    texts = corpus(
        {"AAA": "then the plo vish was there", "BBB": "then the plovish was there"}, extra
    )
    assert fixed(texts) == "then the plovish was there"


def test_a_word_in_three_pieces_is_joined_whole() -> None:
    texts = corpus({"AAA": "he said t ha t he would go", "BBB": "he said that he would go"})
    assert fixed(texts) == "he said that he would go"


def test_rival_readings_keep_the_one_that_leaves_no_fragment() -> None:
    # "tha t he": "that he" leaves words only; "tha the" would leave "tha"
    texts = corpus({"AAA": "he said tha t he would go", "BBB": "he said that he would go"})
    assert fixed(texts) == "he said that he would go"


def test_rival_readings_follow_the_sibling_verse() -> None:
    # "word s hall": "words hall" and "word shall" are both words; the sibling prints the second
    extra = both(["the words of the man", "words of the man", "the hall of the house", "a hall"])
    texts = corpus(
        {"AAA": "and his word s hall be with him", "BBB": "and his word shall be with him"}, extra
    )
    assert fixed(texts) == "and his word shall be with him"


def test_rival_readings_with_no_evidence_are_left_alone() -> None:
    extra = both(["blap is here", "blap is here", "blaps is here", "blaps is here"])
    extra = {
        code: [*lines, "trin is here", "trin is here", "strin is here", "strin is here"]
        for code, lines in extra.items()
    }
    texts = corpus({"AAA": "the blap s trin went", "BBB": "the dog went"}, extra)
    found = find(texts)
    assert not found.changes
    assert [(left.span, left.reason) for left in found.left] == [
        ("blap s trin", "two readings fit equally")
    ]


def test_a_break_shared_by_a_sibling_is_still_joined() -> None:
    # the KJV family and ASV/ERV share many breaks: a sibling printing the same split is no evidence
    texts = corpus(
        {
            "AAA": "they went in t he field",
            "BBB": "they went in t he field",
            "CCC": "they went in the field",
        }
    )
    repair(texts)
    assert texts["AAA"][TEST] == texts["BBB"][TEST] == "they went in the field"


# -- left alone ----------------------------------------------------------------------------


def test_two_words_that_join_into_a_word_are_listed_not_joined() -> None:
    extra = both(
        ["the heart of the man", "a heart", "the art of the man", "an art"], ("AAA", "BBB", "CCC")
    )
    texts = corpus(
        {
            "AAA": "and he art in the field",
            "BBB": "and heart in the field",
            "CCC": "and heart in the field",
        },
        extra,
    )
    found = find(texts)
    assert not found.changes
    assert [(left.span, left.reason) for left in found.left] == [
        ("he art", "both halves are words")
    ]


def test_a_phrase_the_translation_prefers_is_never_joined() -> None:
    # "fallow deer" three times against "fallowdeer" twice: a phrase, not a broken word
    extra: dict[str, Sequence[str]] = {
        "AAA": [
            "the fallowdeer ran",
            "a fallowdeer ran",
            "the fallow deer ran",
            "a fallow deer ran",
        ],
        "BBB": ["the fallowdeer ran", "a fallowdeer ran"],
    }
    texts = corpus({"AAA": "and the fallow deer ran", "BBB": "and the fallowdeer ran"}, extra)
    assert not find(texts).changes


def test_a_rare_name_a_sibling_prints_alone_is_a_word() -> None:
    # "Zephor" stands once in AAA, but the sibling prints it alone: "Zephor a hill" is no break
    extra = both(["Zephora went home", "then Zephora went home"])
    texts = corpus({"AAA": "unto Zephor a hill", "BBB": "unto Zephor, the hill"}, extra)
    assert not find(texts).changes


def test_a_one_letter_word_beside_a_word_printed_elsewhere_is_left_alone() -> None:
    # "a lone": "lone" stands alone in another translation, so this is the real phrase
    extra: dict[str, Sequence[str]] = {
        "AAA": ["the man was alone", "he was alone"],
        "BBB": ["the man was alone", "he was alone"],
        "CCC": ["the lone man", "a tree stood lone"],
    }
    texts = corpus(
        {"AAA": "he saw a lone man", "BBB": "he saw the man alone", "CCC": "he saw a man"}, extra
    )
    found = find(texts)
    assert not found.changes
    assert [left.reason for left in found.left] == [
        "a one-letter word beside a word printed elsewhere"
    ]


def test_a_one_letter_word_whose_neighbour_prefers_the_split_is_left_alone() -> None:
    # "a lone witness": "lone" is printed nowhere else; "lone witness" is, "alone witness" never
    lines = ["he was alone", "they were alone", "she was alone", "a lone witness came"]
    texts = corpus({"AAA": "on a lone witness", "BBB": "on one witness"}, {"AAA": lines, "BBB": []})
    found = find(texts)
    assert not found.changes
    assert [left.reason for left in found.left if left.ref == TEST] == [
        "a one-letter word, and the joined word is not attested beside its neighbours"
    ]


def test_a_one_letter_split_whose_joined_word_fits_is_joined() -> None:
    lines = ["and also the house", "and also the field", "also the man"]
    texts = corpus({"AAA": "and a lso the man", "BBB": "and also the man"}, both(lines))
    assert fixed(texts) == "and also the man"


def test_thin_evidence_is_listed() -> None:
    # "blorped" stands alone only twice and no sibling prints it
    extra = both(["the blorped man", "a blorped man"])
    texts = corpus({"AAA": "the man blorp ed there", "BBB": "the man ran there"}, extra)
    found = find(texts)
    assert not found.changes
    assert [left.span for left in found.left] == ["blorp ed"]


def test_own_counts_alone_suffice_when_the_fragment_is_a_word_nowhere() -> None:
    extra = both(["the blorped man", "a blorped man", "one blorped man"])
    texts = corpus({"AAA": "the man blorp ed there", "BBB": "the man ran there"}, extra)
    assert fixed(texts) == "the man blorped there"


# -- hyphens, apostrophes ------------------------------------------------------------------


def test_a_space_after_a_hyphen_is_removed_when_the_compound_is_printed() -> None:
    extra = {"AAA": ["the sin-offering was there"], "BBB": []}
    texts = corpus({"AAA": "the sin- offering of the man", "BBB": "the gift of the man"}, extra)
    found = find(texts)
    assert [(c.kind, c.after) for c in found.changes] == [("hyphen", "the sin-offering of")]
    assert fixed(texts) == "the sin-offering of the man"


def test_a_space_before_a_hyphen_is_removed_when_a_sibling_prints_the_compound() -> None:
    texts = corpus({"AAA": "when Ben -hadad heard", "BBB": "when Ben-hadad heard"})
    assert fixed(texts) == "when Ben-hadad heard"


def test_a_line_break_hyphen_is_listed_not_changed() -> None:
    extra = both(["a thousand men", "the thousand men"])
    texts = corpus(
        {"AAA": "four hundred thou- sand men", "BBB": "four hundred thousand men"}, extra
    )
    found = find(texts)
    assert not found.changes
    assert [(left.kind, left.span) for left in found.left] == [("hyphen", "thou- sand")]
    assert found.left[0].reason.startswith("line-break hyphen")


def test_a_suspended_hyphen_is_left_alone() -> None:
    texts = corpus({"AAA": "the two- and three-day feasts", "BBB": "the feasts"})
    assert not find(texts).changes


def test_a_split_apostrophe_is_closed_when_the_word_is_printed() -> None:
    extra = both(["his father’s house", "my father’s house"])
    texts = corpus({"AAA": "to his father’ s house", "BBB": "to his father’s house"}, extra)
    assert fixed(texts) == "to his father’s house"


# -- words glued together ------------------------------------------------------------------


def test_a_glued_pair_is_split_when_the_sibling_prints_the_two_words() -> None:
    extra = {"AAA": ["and gave him both of them"], "BBB": []}
    texts = corpus(
        {"AAA": "then he gave himboth of them", "BBB": "then he gave him both of them"}, extra
    )
    found = find(texts)
    assert [(c.kind, c.before, c.after) for c in found.changes] == [
        ("glued", "gave himboth of", "gave him both of")
    ]
    assert fixed(texts) == "then he gave him both of them"


def test_a_glued_pair_no_sibling_prints_is_listed() -> None:
    texts = corpus({"AAA": "then he went withhim away", "BBB": "then he went away"})
    found = find(texts)
    assert not found.changes
    assert [(left.kind, left.span, left.reason) for left in found.left] == [
        ("glued", "withhim", "no sibling prints the two words")
    ]


def test_a_glued_token_a_sibling_prints_hyphenated_is_a_compound() -> None:
    texts = corpus({"AAA": "he went withhim away", "BBB": "he went with-him away"})
    found = find(texts)
    assert not found.changes
    assert [left.reason for left in found.left] == [
        "printed as a compound or the translation's own spelling, not two words"
    ]


def test_a_glued_token_opening_with_a_is_left_alone() -> None:
    # "awork", "afoot", "aside": a- words, not "a" + word
    texts = corpus({"AAA": "he saw aman there", "BBB": "he saw a man there"}, both(["a man went"]))
    assert not find(texts).changes


def test_a_glued_token_printed_twice_is_the_translation_s_own_spelling() -> None:
    lines = ["thehouse is there"]
    texts = corpus(
        {"AAA": "in thehouse there", "BBB": "in the house there"}, {"AAA": lines, "BBB": []}
    )
    assert not find(texts).changes


def test_a_glued_token_with_an_inner_capital_is_split_though_printed_twice() -> None:
    lines = ["theMan went"]
    texts = corpus({"AAA": "of theMan of", "BBB": "of the Man of"}, {"AAA": lines, "BBB": []})
    assert fixed(texts) == "of the Man of"


def test_a_fragment_of_a_broken_word_is_not_split_as_glued() -> None:
    # "dwellin g": "dwellin" splits into "dwell in", but it is half of "dwelling"
    extra = both(["the dwelling of the man", "a dwelling"])
    texts = corpus({"AAA": "they were dwellin g there", "BBB": "they were dwelling there"}, extra)
    found = find(texts)
    assert [c.kind for c in found.changes] == ["split"]
    assert fixed(texts) == "they were dwelling there"


def test_a_missing_space_after_punctuation_is_restored_when_a_sibling_has_it() -> None:
    texts = corpus(
        {
            "AAA": "the burden of Damascus.Behold the man",
            "BBB": "the burden of Damascus. Behold the man",
        }
    )
    found = find(texts)
    assert [(c.kind, c.after) for c in found.changes] == [
        ("punctuation", "of Damascus. Behold the")
    ]
    assert fixed(texts) == "the burden of Damascus. Behold the man"


# -- invariants ----------------------------------------------------------------------------


def many_faults() -> Texts:
    extra = both(["and gave him both of them", "the sin-offering was there"])
    return corpus(
        {
            "AAA": "in t he field an d the sin- offering, Damascus.Behold himboth",
            "BBB": "in the field and the sin-offering, Damascus. Behold him both",
        },
        extra,
    )


def test_a_repair_only_removes_or_inserts_spaces() -> None:
    texts = many_faults()
    before = dict(texts["AAA"])
    found = repair(texts)
    assert {c.kind for c in found.changes} == {"split", "hyphen", "punctuation", "glued"}
    for ref, old in before.items():
        new = texts["AAA"][ref]
        assert new.replace(" ", "") == old.replace(" ", "")


def test_apply_changes_matches_the_repair() -> None:
    texts = many_faults()
    old = texts["AAA"][TEST]
    changes = [c for c in find(texts).changes if c.code == "AAA" and c.ref == TEST]
    assert apply_changes(old, changes).replace(" ", "") == old.replace(" ", "")


def test_a_second_repair_finds_nothing() -> None:
    texts = many_faults()
    assert repair(texts).changes
    assert not repair(texts).changes
    assert not find(texts).changes


# -- the fast guard ----------------------------------------------------------------------


def test_quick_check_flags_a_lone_letter_that_joins_into_a_common_word() -> None:
    texts = corpus({"AAA": "they went in t he field"})
    assert quick_check(texts["AAA"]) == [(TEST, "t he")]


def test_quick_check_flags_a_hyphen_space_in_a_compound_printed_whole() -> None:
    texts = corpus({"AAA": "the sin- offering of the man"}, {"AAA": ["the sin-offering was there"]})
    assert quick_check(texts["AAA"]) == [(TEST, "sin- offering")]


def test_quick_check_passes_clean_text_and_one_letter_words() -> None:
    lines = ["a thousand men", "the two- and three-day feasts", "I said O man"]
    texts = corpus({"AAA": "he saw a man and I said O man"}, {"AAA": lines})
    assert quick_check(texts["AAA"]) == []


# -- files ---------------------------------------------------------------------------------


def translation_file(
    code: str, verses: Mapping[Ref, str], language: str = "en", footnotes: Sequence[Any] = ()
) -> dict[str, Any]:
    chapters: dict[int, list[dict[str, Any]]] = {}
    for (_, chapter, number), text in sorted(verses.items()):
        chapters.setdefault(chapter, []).append(
            {"number": number, "text": text, "is_red_letter": False}
        )
    return {
        "code": code,
        "name": f"Made-up {code}",
        "language": language,
        "copyright": "Made up for a test.",
        "books": [
            {
                "name": "Genesis",
                "abbreviation": "Gen",
                "order_index": 1,
                "chapters": [
                    {
                        "number": n,
                        "verses": vs,
                        "headings": [{"before_verse": 1, "text": "A Made-Up Heading"}],
                        "footnotes": list(footnotes) if n == TEST[1] else [],
                    }
                    for n, vs in sorted(chapters.items())
                ],
            }
        ],
    }


def write_files(
    folder: Path,
    texts: Texts,
    language: str = "en",
    footnotes: Sequence[Any] = (),
    anchored: str = "AAA",
) -> dict[str, Path]:
    """Write ``texts`` as translation files; ``footnotes`` go to the ``anchored`` one only."""
    folder.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for code, verses in texts.items():
        notes = footnotes if code == anchored else ()
        data = translation_file(code, verses, language=language, footnotes=notes)
        path = folder / f"{code}.json"
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        paths[code] = path
    return paths


def test_main_repairs_files_changing_only_verse_text_lines(tmp_path: Path) -> None:
    paths = write_files(tmp_path / "data", many_faults())
    original = paths["AAA"].read_text(encoding="utf-8").splitlines()
    assert main(["--data-dir", str(tmp_path / "data"), "--manifest-dir", str(tmp_path / "m")]) == 0
    repaired = paths["AAA"].read_text(encoding="utf-8").splitlines()
    assert len(repaired) == len(original)
    changed = [(a, b) for a, b in zip(original, repaired, strict=True) if a != b]
    assert len(changed) == 1 and all('"text":' in a and '"text":' in b for a, b in changed)
    rows = (tmp_path / "m" / "broken_words_manifest.csv").read_text(encoding="utf-8").splitlines()
    assert rows[0].startswith("translation,reference,offset,kind,before,after")
    assert len(rows) == 1 + 5  # the five faults, each one row


def test_a_second_main_run_leaves_files_and_manifest_alone(tmp_path: Path) -> None:
    write_files(tmp_path / "data", many_faults())
    args = ["--data-dir", str(tmp_path / "data"), "--manifest-dir", str(tmp_path / "m")]
    assert main(args) == 0
    snapshot = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert main(args) == 0
    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()} == snapshot


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    write_files(tmp_path / "data", many_faults())
    snapshot = {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()}
    assert (
        main(
            [
                "--dry-run",
                "--data-dir",
                str(tmp_path / "data"),
                "--manifest-dir",
                str(tmp_path / "m"),
            ]
        )
        == 0
    )
    assert {p: p.read_bytes() for p in sorted(tmp_path.rglob("*")) if p.is_file()} == snapshot


def test_a_translation_with_anchored_notes_is_never_changed(tmp_path: Path) -> None:
    footnotes = [{"verse_number": 1, "char_offset": 5, "text": "A made-up note."}]
    paths = write_files(tmp_path / "data", many_faults(), footnotes=footnotes)
    before = paths["AAA"].read_bytes()
    assert main(["--data-dir", str(tmp_path / "data"), "--manifest-dir", str(tmp_path / "m")]) == 0
    assert paths["AAA"].read_bytes() == before


def test_a_translation_with_a_notes_file_is_never_changed(tmp_path: Path) -> None:
    paths = write_files(tmp_path / "data", many_faults())
    (tmp_path / "data" / "notes").mkdir()
    (tmp_path / "data" / "notes" / "AAA.json").write_text('{"translation": "AAA", "notes": []}\n')
    before = paths["AAA"].read_bytes()
    assert main(["--data-dir", str(tmp_path / "data"), "--manifest-dir", str(tmp_path / "m")]) == 0
    assert paths["AAA"].read_bytes() == before


def test_only_limits_which_translations_change(tmp_path: Path) -> None:
    texts = many_faults()
    texts["BBB"][TEST] = "in t he field"
    paths = write_files(tmp_path / "data", texts)
    before = paths["BBB"].read_bytes()
    args = [
        "--only",
        "AAA",
        "--data-dir",
        str(tmp_path / "data"),
        "--manifest-dir",
        str(tmp_path / "m"),
    ]
    assert main(args) == 0
    assert paths["BBB"].read_bytes() == before
    assert "in the field" in paths["AAA"].read_text(encoding="utf-8")


def test_a_non_english_text_is_neither_changed_nor_evidence(tmp_path: Path) -> None:
    texts = corpus({"AAA": "they went in t he field", "GRK": "they went in t he field"})
    paths = write_files(tmp_path / "data", {"GRK": texts["GRK"]}, language="grc")
    paths |= write_files(tmp_path / "data", {"AAA": texts["AAA"]})
    before = paths["GRK"].read_bytes()
    assert main(["--data-dir", str(tmp_path / "data"), "--manifest-dir", str(tmp_path / "m")]) == 0
    assert paths["GRK"].read_bytes() == before
    # with no English sibling to corroborate, "t he" rests on AAA's own counts alone: joined
    assert "in the field" in paths["AAA"].read_text(encoding="utf-8")


def test_evidence_dir_supplies_siblings_without_being_changed(tmp_path: Path) -> None:
    texts = corpus({"AAA": "they went in t he field", "BBB": "they went in t he field"})
    paths = write_files(tmp_path / "data", {"AAA": texts["AAA"]})
    evidence = write_files(tmp_path / "evidence", {"BBB": texts["BBB"]})
    before = evidence["BBB"].read_bytes()
    args = ["--data-dir", str(tmp_path / "data"), "--evidence-dir", str(tmp_path / "evidence")]
    assert main([*args, "--manifest-dir", str(tmp_path / "m")]) == 0
    assert evidence["BBB"].read_bytes() == before
    assert "in the field" in paths["AAA"].read_text(encoding="utf-8")
