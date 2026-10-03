"""The broken- and glued-word repair (scripts/fix_broken_words.py), on made-up text only.

Each corpus is two or three made-up "translations" that share a filler of invented words (so
the common words have counts) and differ in one test verse. Every word is invented except the
one-letter words "a", "I" and "O", which the one-letter rules need.
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
    "zan dor plim sa tek ve wud gor bi tem",
    "dor gim sorn ke bi lum zan bi hiz brim",
    "kel ul faw borb ov tem in dor fen",
    "tem kve sa in dor brim ov dor plim",
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
    texts = corpus({"AAA": "zan kel p lim fen", "BBB": "zan kel plim fen"})
    found = find(texts)
    assert [(c.code, c.kind, c.before, c.after) for c in found.changes] == [
        ("AAA", "split", "kel p lim fen", "kel plim fen")
    ]
    assert fixed(texts) == "zan kel plim fen"


def test_a_last_letter_split_off_is_joined() -> None:
    texts = corpus({"AAA": "zan kel bri m fen", "BBB": "zan kel brim fen"})
    assert fixed(texts) == "zan kel brim fen"


def test_a_word_split_inside_is_joined() -> None:
    extra = both(["dor plovish ov dor fen", "a plovish ov dor brim"])
    texts = corpus({"AAA": "zan dor plo vish tek ve", "BBB": "zan dor plovish tek ve"}, extra)
    assert fixed(texts) == "zan dor plovish tek ve"


def test_a_word_in_three_pieces_is_joined_whole() -> None:
    texts = corpus({"AAA": "zan s or n bi gor", "BBB": "zan sorn bi gor"})
    assert fixed(texts) == "zan sorn bi gor"


def test_rival_readings_keep_the_one_that_leaves_no_fragment() -> None:
    # "te k ve": "tek ve" leaves words only; "te kve" would leave "te"
    texts = corpus({"AAA": "ul sa te k ve wud gor", "BBB": "ul sa tek ve wud gor"})
    assert fixed(texts) == "ul sa tek ve wud gor"


def test_rival_readings_follow_the_sibling_verse() -> None:
    # "kel s orn": "kels orn" and "kel sorn" are both words, and the translation prints
    # "kels orn" elsewhere; the sibling prints "kel sorn" in this verse, and that decides it
    extra = both(["dor kels orn plim", "zan kels orn plim"])
    texts = corpus({"AAA": "zan hiz kel s orn bi ul", "BBB": "zan hiz kel sorn bi ul"}, extra)
    assert fixed(texts) == "zan hiz kel sorn bi ul"


def test_rival_readings_with_no_evidence_are_left_alone() -> None:
    lines = ["blap ka", "blap ka", "blaps ka", "blaps ka", "trin ka", "trin ka", "strin ka"]
    texts = corpus({"AAA": "dor blap s trin gor", "BBB": "dor zib gor"}, both([*lines, "strin ka"]))
    found = find(texts)
    assert not found.changes
    assert [(left.span, left.reason) for left in found.left] == [
        ("blap s trin", "two readings fit equally")
    ]


def test_a_break_shared_by_a_sibling_is_still_joined() -> None:
    # translations of one family share many breaks: a sibling printing the same split is no
    # evidence against joining it
    texts = corpus(
        {"AAA": "zan kel p lim fen", "BBB": "zan kel p lim fen", "CCC": "zan kel plim fen"}
    )
    repair(texts)
    assert texts["AAA"][TEST] == texts["BBB"][TEST] == "zan kel plim fen"


# -- left alone ----------------------------------------------------------------------------


def test_two_words_that_join_into_a_word_are_listed_not_joined() -> None:
    lines = ["dor feprif ov dor plim", "a feprif", "dor rif ov dor plim", "a rif"]
    extra = both([*lines, "dor fep ov dor brim", "a fep"], ("AAA", "BBB", "CCC"))
    texts = corpus(
        {
            "AAA": "kel fep rif in dor fen",
            "BBB": "kel feprif in dor fen",
            "CCC": "kel feprif in dor fen",
        },
        extra,
    )
    found = find(texts)
    assert not found.changes
    assert [(left.span, left.reason) for left in found.left] == [
        ("fep rif", "both halves are words")
    ]


def test_a_phrase_the_translation_prefers_is_never_joined() -> None:
    # "zorbel k" three times against "zorbelk" twice: a phrase, not a broken word, though the
    # sibling prints "zorbelk" and a lone letter is never a word
    extra: dict[str, Sequence[str]] = {
        "AAA": ["dor zorbelk gor", "a zorbelk gor", "dor zorbel k gor", "a zorbel k gor"],
        "BBB": ["dor zorbelk gor", "a zorbelk gor"],
    }
    texts = corpus({"AAA": "kel dor zorbel k gor", "BBB": "kel dor zorbelk gor"}, extra)
    assert not find(texts).changes


def test_a_rare_name_a_sibling_prints_alone_is_a_word() -> None:
    # "Zephor" stands once in AAA, but one sibling prints it alone: "Zephor sa" is no break,
    # though another sibling prints "Zephorsa" in the same verse
    extra = both(["Zephorsa dor brim", "zan Zephorsa dor brim"], ("AAA", "BBB", "CCC"))
    texts = corpus(
        {"AAA": "wa Zephor sa brim", "BBB": "wa Zephor, dor brim", "CCC": "wa Zephorsa brim"},
        extra,
    )
    assert not find(texts).changes


def test_a_one_letter_word_beside_a_word_printed_elsewhere_is_left_alone() -> None:
    # "a loppa": "loppa" stands alone in another translation: the real phrase, then
    extra: dict[str, Sequence[str]] = {
        "AAA": ["dor plim sa aloppa", "ul sa aloppa"],
        "BBB": ["dor plim sa aloppa", "ul sa aloppa"],
        "CCC": ["dor loppa plim", "a borb fen loppa"],
    }
    texts = corpus(
        {"AAA": "ul faw a loppa plim", "BBB": "ul faw dor plim aloppa", "CCC": "ul faw a plim"},
        extra,
    )
    found = find(texts)
    assert not found.changes
    assert [left.reason for left in found.left] == [
        "a one-letter word beside a word printed elsewhere"
    ]


def test_a_one_letter_word_whose_neighbour_prefers_the_split_is_left_alone() -> None:
    # "a loppa grent": "loppa" is printed nowhere else; "loppa grent" is, "aloppa grent" never
    lines = ["ul sa aloppa", "tem sa aloppa", "zan sa aloppa", "a loppa grent gor"]
    texts = corpus({"AAA": "wa a loppa grent", "BBB": "wa ka grent"}, {"AAA": lines, "BBB": []})
    found = find(texts)
    assert not found.changes
    assert [left.reason for left in found.left if left.ref == TEST] == [
        "a one-letter word, and the joined word is not attested beside its neighbours"
    ]


def test_a_one_letter_split_whose_joined_word_fits_is_joined() -> None:
    lines = ["kel alsom dor brim", "kel alsom dor fen", "alsom dor plim"]
    texts = corpus({"AAA": "kel a lsom dor plim", "BBB": "kel alsom dor plim"}, both(lines))
    assert fixed(texts) == "kel alsom dor plim"


def test_thin_evidence_is_listed() -> None:
    # "blorped" stands alone only twice and no sibling prints it
    extra = both(["dor blorped plim", "a blorped plim"])
    texts = corpus({"AAA": "dor plim blorp ed tek", "BBB": "dor plim zib tek"}, extra)
    found = find(texts)
    assert not found.changes
    assert [left.span for left in found.left] == ["blorp ed"]


def test_own_counts_alone_suffice_when_the_fragment_is_a_word_nowhere() -> None:
    extra = both(["dor blorped plim", "a blorped plim", "zan blorped plim"])
    texts = corpus({"AAA": "dor plim blorp ed tek", "BBB": "dor plim zib tek"}, extra)
    assert fixed(texts) == "dor plim blorped tek"


# -- hyphens, apostrophes ------------------------------------------------------------------


def test_a_space_after_a_hyphen_is_removed_when_the_compound_is_printed() -> None:
    extra = {"AAA": ["dor pask-trell gor"], "BBB": []}
    texts = corpus({"AAA": "dor pask- trell ov dor plim", "BBB": "dor zib ov dor plim"}, extra)
    found = find(texts)
    assert [(c.kind, c.after) for c in found.changes] == [("hyphen", "dor pask-trell ov")]
    assert fixed(texts) == "dor pask-trell ov dor plim"


def test_a_space_before_a_hyphen_is_removed_when_a_sibling_prints_the_compound() -> None:
    texts = corpus({"AAA": "wa Gor -mesh faw", "BBB": "wa Gor-mesh faw"})
    assert fixed(texts) == "wa Gor-mesh faw"


def test_a_line_break_hyphen_is_listed_not_changed() -> None:
    extra = both(["a vordask plim", "dor vordask plim"])
    texts = corpus({"AAA": "kel ul vor- dask plim", "BBB": "kel ul vordask plim"}, extra)
    found = find(texts)
    assert not found.changes
    assert [(left.kind, left.span) for left in found.left] == [("hyphen", "vor- dask")]
    assert found.left[0].reason.startswith("line-break hyphen")


def test_a_suspended_hyphen_is_left_alone() -> None:
    texts = corpus({"AAA": "dor pem- obo trell-zan fen", "BBB": "dor fen"})
    assert not find(texts).changes


def test_a_split_apostrophe_is_closed_when_the_word_is_printed() -> None:
    extra = both(["hiz brimmo’s fen", "dor brimmo’s fen"])
    texts = corpus({"AAA": "wa hiz brimmo’ s fen", "BBB": "wa hiz brimmo’s fen"}, extra)
    assert fixed(texts) == "wa hiz brimmo’s fen"


# -- words glued together ------------------------------------------------------------------


def test_a_glued_pair_is_split_when_the_sibling_prints_the_two_words() -> None:
    extra = {"AAA": ["kel faw ul borb ov tem"], "BBB": []}
    texts = corpus({"AAA": "zan ul faw ulborb ov tem", "BBB": "zan ul faw ul borb ov tem"}, extra)
    found = find(texts)
    assert [(c.kind, c.before, c.after) for c in found.changes] == [
        ("glued", "faw ulborb ov", "faw ul borb ov")
    ]
    assert fixed(texts) == "zan ul faw ul borb ov tem"


def test_a_glued_pair_no_sibling_prints_is_listed() -> None:
    texts = corpus({"AAA": "zan ul gor dorplim ka", "BBB": "zan ul gor ka"})
    found = find(texts)
    assert not found.changes
    assert [(left.kind, left.span, left.reason) for left in found.left] == [
        ("glued", "dorplim", "no sibling prints the two words")
    ]


def test_a_glued_token_a_sibling_prints_hyphenated_is_a_compound() -> None:
    texts = corpus({"AAA": "zan ul gor dorplim ka", "BBB": "zan ul gor dor-plim ka"})
    found = find(texts)
    assert not found.changes
    assert [left.reason for left in found.left] == [
        "printed as a compound or the translation's own spelling, not two words"
    ]


def test_a_glued_token_opening_with_a_is_left_alone() -> None:
    # a- words (the archaic "awork", "afoot"), not "a" + word
    texts = corpus({"AAA": "ul sa ador tek", "BBB": "ul sa a dor tek"}, both(["a dor gor"]))
    assert not find(texts).changes


def test_a_glued_token_printed_twice_is_the_translation_s_own_spelling() -> None:
    lines = ["dorbrim ka tek"]
    texts = corpus({"AAA": "in dorbrim tek", "BBB": "in dor brim tek"}, {"AAA": lines, "BBB": []})
    assert not find(texts).changes


def test_a_glued_token_with_an_inner_capital_is_split_though_printed_twice() -> None:
    lines = ["dorPlim gor"]
    texts = corpus({"AAA": "ov dorPlim ov", "BBB": "ov dor Plim ov"}, {"AAA": lines, "BBB": []})
    assert fixed(texts) == "ov dor Plim ov"


def test_a_fragment_of_a_broken_word_is_not_split_as_glued() -> None:
    # "dorul k": "dorul" splits into "dor ul", which a sibling prints, but it is half of "dorulk"
    extra = both(["dor dorulk ov dor plim", "a dorulk", "dor ul faw"], ("AAA", "BBB", "CCC"))
    texts = corpus(
        {"AAA": "ka wa dorul k tek", "BBB": "ka wa dorulk tek", "CCC": "ka wa dor ul tek"}, extra
    )
    found = find(texts)
    assert [c.kind for c in found.changes] == ["split"]
    assert fixed(texts) == "ka wa dorulk tek"


def test_a_missing_space_after_punctuation_is_restored_when_a_sibling_has_it() -> None:
    texts = corpus(
        {"AAA": "dor plim ov Pashur.Vel dor brim", "BBB": "dor plim ov Pashur. Vel dor brim"}
    )
    found = find(texts)
    assert [(c.kind, c.after) for c in found.changes] == [("punctuation", "ov Pashur. Vel dor")]
    assert fixed(texts) == "dor plim ov Pashur. Vel dor brim"


# -- invariants ----------------------------------------------------------------------------


def many_faults() -> Texts:
    extra = both(["kel faw ul borb ov tem", "dor pask-trell gor"])
    return corpus(
        {
            "AAA": "kel p lim fen bri m dor pask- trell, Pashur.Vel ulborb",
            "BBB": "kel plim fen brim dor pask-trell, Pashur. Vel ul borb",
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


def test_kinds_limits_the_repairs_to_one_kind() -> None:
    texts = many_faults()
    found = repair(texts, kinds="hyphen")
    assert [c.kind for c in found.changes] == ["hyphen"]
    assert texts["AAA"][TEST].startswith("kel p lim fen bri m dor pask-trell,")


def test_a_second_repair_finds_nothing() -> None:
    texts = many_faults()
    assert repair(texts).changes
    assert not repair(texts).changes
    assert not find(texts).changes


# -- the fast guard ------------------------------------------------------------------------


def test_quick_check_flags_a_lone_letter_that_joins_into_a_common_word() -> None:
    texts = corpus({"AAA": "zan kel p lim fen"})
    assert quick_check(texts["AAA"]) == [(TEST, "p lim")]


def test_quick_check_flags_a_hyphen_space_in_a_compound_printed_whole() -> None:
    texts = corpus({"AAA": "dor pask- trell ov dor plim"}, {"AAA": ["dor pask-trell gor"]})
    assert quick_check(texts["AAA"]) == [(TEST, "pask- trell")]


def test_quick_check_passes_clean_text_and_one_letter_words() -> None:
    lines = ["a vordask plim", "dor pem- obo trell-zan fen", "I faw O plim"]
    texts = corpus({"AAA": "ul sa a dor kel I faw O plim"}, {"AAA": lines})
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
    texts["BBB"][TEST] = "kel p lim fen"
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
    assert "kel plim fen" in paths["AAA"].read_text(encoding="utf-8")


def test_a_non_english_text_is_neither_changed_nor_evidence(tmp_path: Path) -> None:
    texts = corpus({"AAA": "zan kel p lim fen", "GRK": "zan kel p lim fen"})
    paths = write_files(tmp_path / "data", {"GRK": texts["GRK"]}, language="grc")
    paths |= write_files(tmp_path / "data", {"AAA": texts["AAA"]})
    before = paths["GRK"].read_bytes()
    assert main(["--data-dir", str(tmp_path / "data"), "--manifest-dir", str(tmp_path / "m")]) == 0
    assert paths["GRK"].read_bytes() == before
    # with no English sibling to corroborate, "p lim" rests on AAA's own counts alone: joined
    assert "kel plim fen" in paths["AAA"].read_text(encoding="utf-8")


def test_evidence_dir_supplies_siblings_without_being_changed(tmp_path: Path) -> None:
    texts = corpus({"AAA": "zan kel p lim fen", "BBB": "zan kel p lim fen"})
    paths = write_files(tmp_path / "data", {"AAA": texts["AAA"]})
    evidence = write_files(tmp_path / "evidence", {"BBB": texts["BBB"]})
    before = evidence["BBB"].read_bytes()
    args = ["--data-dir", str(tmp_path / "data"), "--evidence-dir", str(tmp_path / "evidence")]
    assert main([*args, "--manifest-dir", str(tmp_path / "m")]) == 0
    assert evidence["BBB"].read_bytes() == before
    assert "kel plim fen" in paths["AAA"].read_text(encoding="utf-8")


def test_a_code_in_both_data_and_evidence_is_refused(tmp_path: Path) -> None:
    texts = corpus({"AAA": "zan kel p lim fen"})
    paths = write_files(tmp_path / "data", texts)
    write_files(tmp_path / "evidence", texts)
    before = paths["AAA"].read_bytes()
    args = ["--data-dir", str(tmp_path / "data"), "--evidence-dir", str(tmp_path / "evidence")]
    assert main([*args, "--manifest-dir", str(tmp_path / "m")]) == 1
    assert paths["AAA"].read_bytes() == before
