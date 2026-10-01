"""The PDF quirk fixes, each switchable so the cross-check can compare a raw parse.

Every rule here was measured on the source PDF (docs/v8/SPEC.md §3) and is kept as narrow as
the evidence allows: a fix that fires where it shouldn't shows up as a *fix regression* in the
cross-check (the raw parse agreed with the EPUB, the fixed one doesn't).
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

_WS = re.compile(r"\s+")
_HYPHEN = "-"
_EM_DASH = "—"


@dataclass(frozen=True, slots=True)
class Fixes:
    """Which quirk fixes run. ``Fixes.none()`` is the raw parse the cross-check compares."""

    letter_spacing: bool = True
    fractions: bool = True
    line_hyphens: bool = True
    compound_hyphens: bool = True
    table_split_rows: bool = True

    @classmethod
    def none(cls) -> Fixes:
        return cls(False, False, False, False, False)


def collapse(text: str) -> str:
    return _WS.sub(" ", text)


class PublicWords:
    """The committed public-domain translations as a word list. Built once per run.

    ``words`` splits at hyphens; ``tokens`` and ``phrases`` (2–3 tokens) keep whole
    tokens. These files share some of the PDF's broken words ("h im", "Is rael"), so a
    phrase only counts *against* its joined form ("him" outnumbers "h im"; "money changers"
    outnumbers "moneychangers").
    """

    def __init__(self, texts: Iterable[str]) -> None:
        self.words: Counter[str] = Counter()
        self.tokens: Counter[str] = Counter()
        self.phrases: Counter[tuple[str, ...]] = Counter()
        for text in texts:
            self.words.update(words_of(text))
            tokens = [w for w in (letters(t) for t in text.split()) if w]
            self.tokens.update(tokens)
            for size in (2, 3):
                self.phrases.update(
                    tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)
                )

    def prefers_phrase(self, pieces: list[str]) -> bool:
        return self.phrases[tuple(pieces)] > self.tokens["".join(pieces)]


class Vocabulary:
    """Which letter runs are words, for telling a broken word from a real phrase.

    Sources: the public translations' words, and the PDF's own *trusted* text (outside the
    places broken words occur). A *piece* counts as a word only when the PDF prints it in
    trusted text or the public texts use it often; a *joined* word needs only to occur once
    anywhere; a run the PDF prints as a phrase in trusted text ("money changers") is never
    joined.
    """

    LETTER_WORDS = frozenset({"a", "i", "o"})
    COMMON_IN_PUBLIC = 20

    def __init__(self, public: PublicWords, pdf_texts: Iterable[str]) -> None:
        self._public = public
        self._pdf: Counter[str] = Counter()
        self._phrases: set[tuple[str, ...]] = set()
        for text in pdf_texts:
            self._pdf.update(words_of(text))
            tokens = [w for w in (letters(t) for t in text.split()) if w]
            for size in (2, 3):
                self._phrases.update(
                    tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)
                )

    def is_piece_word(self, word: str) -> bool:
        if len(word) == 1:
            return word in self.LETTER_WORDS
        return self._pdf[word] > 0 or self._public.words[word] >= self.COMMON_IN_PUBLIC

    def is_word(self, word: str) -> bool:
        return self._pdf[word] > 0 or self._public.words[word] > 0

    def broken(self, pieces: list[str], hyphenated: str | None = None) -> bool:
        """Do ``pieces`` (lower-case letters) look like one word split by spaces?

        ``hyphenated``: the joined run as printed, when it holds a hyphen ("Ben-kaz" + "ar").
        Its hyphen-split words must each be a word ("ben", "kazar"): a compound name is a word
        only in parts.
        """
        if len(pieces) < 2 or all(self.is_piece_word(p) for p in pieces):
            return False
        if tuple(pieces) in self._phrases or self._public.prefers_phrase(pieces):
            return False  # a real phrase ("money changers"), not a broken word
        if hyphenated is not None:
            return all(self.is_word(w) for w in words_of(hyphenated))
        return self.is_word("".join(pieces))


def words_of(text: str) -> list[str]:
    """Lower-case words, split at spaces and hyphens/dashes; tokens with digits dropped."""
    return [w for w in (letters(t) for t in re.split(r"[\s\-—–]+", text)) if w]


def letters(token: str) -> str:
    """A token's word (lower case, punctuation stripped); "" for anything with a digit."""
    if any(c.isdigit() for c in token):
        return ""
    return "".join(c for c in token.lower() if c.isalpha() or c in "’'")


_CHUNKS = re.compile(r"( {2,})")
_CLOSING = frozenset(".,;:!?)’”")
_OPENING = frozenset("(“‘[")
_APOSTROPHES = ("’", "'")


def letter_spacing(
    text: str,
    vocabulary: Vocabulary,
    *,
    whole_item: bool,
    glued_tail: bool = False,
    apostrophe_splits: bool = True,
) -> str | None:
    """Join words the text layer broke with spaces ("g o o d .", "prophes y.", "ask ing").

    Justification and the italic font spread some words glyph by glyph, so their pieces
    arrive single-spaced. In roman text the broken word always opens the item (the last
    word of a verse, first on a justified line); in italic text (psalm titles) it can sit
    anywhere (``whole_item``). The longest run of pieces that joins into a known word — where
    at least one piece is not a word on its own — is joined ("for him", "I am a", "money
    lender" are left alone). A lone word followed by spaced punctuation
    ("thighs .") closes up. ``glued_tail``: the item's last letters continue in the next item
    (small caps: "be the L" + "ORD"), so its last piece is not a fragment.
    ``apostrophe_splits=False``: a word split just after an apostrophe ("Name’ s") is left as
    printed. Returns the fixed text, or None when nothing changed.
    """
    parts = _CHUNKS.split(text)
    changed = False
    for index in range(0, len(parts), 2):
        if index and not whole_item:
            break
        last = index == len(parts) - 1
        fixed = _join_chunk(
            parts[index],
            vocabulary,
            at_start=index == 0,
            keep_last=glued_tail and last,
            anywhere=whole_item,
            apostrophe_splits=apostrophe_splits,
        )
        if fixed != parts[index]:
            parts[index], changed = fixed, True
    return "".join(parts) if changed else None


def _join_chunk(
    chunk: str,
    vocabulary: Vocabulary,
    *,
    at_start: bool,
    keep_last: bool,
    anywhere: bool,
    apostrophe_splits: bool = True,
) -> str:
    lead = chunk[: len(chunk) - len(chunk.lstrip())]
    tail = chunk[len(chunk.rstrip()) :]
    pieces = chunk.strip().split(" ")
    if not pieces or pieces == [""]:
        return chunk
    kept = pieces.pop() if keep_last and len(pieces) > 1 else None
    if at_start and len(pieces) >= 2 and not re.search(r"\.\s+\.", chunk):  # an ellipsis
        # closing punctuation spaced off its word ("thighs .", "waves , “Silence!") closes up
        merged = [pieces[0]]
        for piece in pieces[1:]:
            if piece and all(c in _CLOSING for c in piece) and letters(merged[-1]):
                merged[-1] += piece
            else:
                merged.append(piece)
        pieces = merged
    out: list[str] = []
    i = 0
    opening = at_start and len(pieces) >= 3 and all(c in _OPENING for c in pieces[0])
    if opening:  # "( s e e the river": the bracket opens the broken word, spaced off it
        out.append(pieces[0])
        i = 1
    while i < len(pieces):
        if i > int(opening) and not anywhere:  # outside italic text a broken word opens it
            out.extend(pieces[i:])
            break
        for size in range(min(len(pieces) - i, 8), 1, -1):
            run = pieces[i : i + size]
            if not apostrophe_splits and any(p.endswith(_APOSTROPHES) for p in run[:-1]):
                continue
            words = [letters(p) for p in run]
            while words and not any(c.isalnum() for c in run[len(words) - 1]):
                words.pop()  # trailing punctuation pieces (" .") join along
            joined = "".join(run)
            hyphenated = joined if _HYPHEN in joined else None
            if words and all(words) and vocabulary.broken(words, hyphenated):
                if opening and i == 1:
                    out[0] += joined
                else:
                    out.append(joined)
                i += size
                break
        else:
            out.append(pieces[i])
            i += 1
    if kept is not None:
        out.append(kept)
    return lead + " ".join(out) + tail


_ELLIPSIS = re.compile(r"\.\s+\.")  # ". . ." is a real ellipsis, spaced on purpose


def unspace(
    text: str,
    vocabulary: Vocabulary,
    *,
    italic: bool,
    first: bool,
    justified: bool,
    glued: bool = False,
    anywhere: bool = False,
    apostrophe_splits: bool = True,
) -> str | None:
    """One item's text with broken words joined, or None when nothing changed.

    Where broken words occur: italic items (anywhere in them), and the first item of a
    justified line, where a real word gap is double and a single space is a glyph gap. An
    item of punctuation alone, spread by justification (") . " after a "*"), closes up.
    ``glued``: the item's last letters continue in the next item (small caps). ``anywhere``:
    read the whole item as italic text is read (the notes' justified lines);
    ``apostrophe_splits``: see ``letter_spacing``.
    """
    bare = text.strip()
    if bare and not any(c.isalnum() for c in bare) and not _ELLIPSIS.search(bare) and " " in bare:
        return text.replace(bare, bare.replace(" ", ""))
    if not (italic or anywhere or (first and justified)):
        return None
    return letter_spacing(
        text,
        vocabulary,
        whole_item=italic or anywhere,
        glued_tail=glued,
        apostrophe_splits=apostrophe_splits,
    )


def fraction(numerator: str, denominator: str, *, fixed: bool) -> str:
    """Small-digit "1" "/" "2" → "½" (or "1/2" in the raw parse, or n⁄d with no glyph)."""
    if not fixed:
        return f"{numerator}/{denominator}"
    glyph = _VULGAR.get((numerator, denominator))
    return glyph if glyph is not None else f"{numerator}⁄{denominator}"


def _vulgar_fractions() -> dict[tuple[str, str], str]:
    table: dict[tuple[str, str], str] = {}
    for code in range(0x00BC, 0x00BF):
        _add_fraction(table, chr(code))
    for code in range(0x2150, 0x215F):
        _add_fraction(table, chr(code))
    return table


def _add_fraction(table: dict[tuple[str, str], str], glyph: str) -> None:
    decomposed = unicodedata.normalize("NFKD", glyph)
    if "⁄" in decomposed:
        num, den = decomposed.split("⁄")
        if num.isdigit() and den.isdigit():
            table[(num, den)] = glyph


_VULGAR = _vulgar_fractions()


class CompoundRepair:
    """Put back the first hyphen of a compound the PDF prints fused ("fatherin-law").

    The PDF drops some hyphens outright (the page itself prints them closed). Most of those
    leave a valid spelling ("cupbearer", "coworker") and are kept as printed. One leaves a
    non-word, and the PDF itself proves the repair: it prints the same hyphenated tail with
    other heads ("daughter-in-law", "son-in-law"), the head is a word it prints on its own
    ("father"), and the fused head ("fatherin") never stands alone anywhere in the book.
    """

    def __init__(self, lines: Iterable[str]) -> None:
        standalone: set[str] = set()
        compounds: set[str] = set()
        for line in lines:
            for token in _TOKEN.findall(line):
                lower = token.lower()
                (compounds if "-" in lower else standalone).add(lower)
        self._standalone = standalone
        # "in-law" from "daughter-in-law": tails that follow a head in two-hyphen compounds
        self._tails = {c.split("-", 1)[1] for c in compounds if c.count("-") >= 2}

    def repair(self, text: str) -> tuple[str, int]:
        count = 0

        def fix(match: re.Match[str]) -> str:
            nonlocal count
            token = match.group(0)
            head, rest = token.split("-", 1)
            for tail in self._tails:
                first, tail_rest = tail.split("-", 1)
                lower = head.lower()
                if rest.lower() != tail_rest or not lower.endswith(first) or lower == first:
                    continue
                stem = head[: -len(first)]
                if stem.lower() in self._standalone and lower not in self._standalone:
                    count += 1
                    return f"{stem}-{head[-len(first) :]}-{rest}"
            return token

        return _TOKEN_WITH_HYPHEN.sub(fix, text), count


_TOKEN = re.compile(r"[A-Za-z]+(?:-[A-Za-z]+)*")
_TOKEN_WITH_HYPHEN = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+)+\b")


def line_joiner(left: str, right: str, fixes: Fixes, *, wrapped: bool) -> str:
    """What goes between the end of one line and the start of the next.

    ``wrapped`` says the first line ran to the right margin, so the break is only a wrap. A
    short line (poetry, a paragraph's end) is a real break: it always takes a space, even
    beside an em dash ("forever—" / "the commitment…" is two poetic lines).
    """
    tail = left.rstrip()
    head = right.lstrip()
    if not wrapped:
        return " "
    if fixes.line_hyphens:
        # The NLT sets em dashes closed; a line break beside one is never a space.
        if tail.endswith(_EM_DASH) or head.startswith(_EM_DASH):
            return ""
        if tail.endswith(_HYPHEN) and head[:1].isalnum():
            return ""
    return " "
