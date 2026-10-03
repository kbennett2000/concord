#!/usr/bin/env python3
"""One-shot cleanup — words broken by a stray space, and words glued together.

The committed English translations carry their source text layer's word breaks: a word
split by a stray space ("in t he ark", KJV Gen 6:14; "sin- offering"; "Ben -hadad";
"father’ s"), and, far more rarely, two words run together ("himboth", "Damascus.Behold").
They break reading, keyword search (FTS) and the WEB embeddings, which all read verse text.

This script repairs them with evidence and nothing else: a broken word loses its stray
space(s), a glued pair gains one space, and no other character, verse or heading changes.
The evidence is the translation's own word counts and the same verse in the sibling
translations. The rules are the EMB converter's (``emb_convert.clean``: a broken word has a
piece that is no word, and a phrase the text prefers is never joined) restated for whole
translations:

* A *piece is a word* when it stands alone at least twice in the translation (not counting
  places where it joins a neighbour into a word), when it is "a", "A", "I" or "O", or when a
  sibling verse prints it without the same partner (rare names: "Sephar a mount").
* A *run* of 2-3 pieces is joined when the joined form stands alone at least twice, at least
  one piece is no word, the translation does not print the pieces as a phrase more often than
  as the word ("fallow deer"), and the word is corroborated: a sibling verse prints it, or
  the translation prints it thrice or more and the fragment is a word nowhere.
  A one-letter word beside a word printed anywhere else is the real phrase ("a lone witness").
* Where pieces could join two ways ("tha t he", "word s hall"), the reading that leaves no
  fragment wins, next the reading whose word pairs the sibling verse prints; a tie is listed.
* "X- y" / "X -y" closes up when "X-y" is printed elsewhere in the translation or in the
  sibling verse; a line-break hyphen ("thou- sand") is listed, as the hyphen would have to go.
* A glued token is split in two when nothing else prints it, it splits exactly one way into
  two common words of the translation, the translation prints that phrase elsewhere and a
  sibling verse prints the two words side by side. A sentence run into the next
  ("Damascus.Behold") gets its space back when the sibling verse has it.

Both halves words ("he art", "in to"), thin evidence and ties are left alone and listed.

    uv run python scripts/fix_broken_words.py --dry-run      # detect and count; write nothing
    uv run python scripts/fix_broken_words.py --kinds glued  # apply one kind of repair
    uv run python scripts/fix_broken_words.py                # apply both

Every applying run repeats until nothing more is found, so a second run is a no-op, and only
an applying run touches the manifest: it appends its changes to broken_words_manifest.csv and
rewrites the .md summary. Files round-trip byte-identically through
``json.dumps(indent=2, ensure_ascii=False)``, so a diff shows only the repaired text lines.
A translation with character-anchored notes (a ``notes/<CODE>.json`` beside it, or footnotes
with a ``char_offset``) is never changed: a space removed or added would move every note
anchored after it. Non-English texts are neither changed nor used as evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from bisect import bisect_right
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any, NamedTuple

Ref = tuple[int, int, int]  # (book order_index, chapter, verse): what sibling translations share

OPENING = "([“‘\"'"
CLOSING = ".,;:!?)]’”\"'"
APOSTROPHES = ("’", "'")
LETTER_WORDS = frozenset({"a", "A", "I", "O"})
COMMON = 20  # stands alone this often: a word beyond doubt
TIE = 0.7  # two readings whose bigram scores differ by less than this are a tie
BROKEN = ("split", "hyphen", "apostrophe")
GLUED = ("glued", "punctuation")
KINDS = {"broken": BROKEN, "glued": GLUED, "hyphen": ("hyphen",), "all": BROKEN + GLUED}

BOTH_WORDS = "both halves are words"
THIN = "thin evidence: the word stands alone fewer than three times and no sibling prints it"
ONE_LETTER = "a one-letter word beside a word printed elsewhere"
ONE_LETTER_CONTEXT = "a one-letter word, and the joined word is not attested beside its neighbours"
COMPOUND = "printed as a compound or the translation's own spelling, not two words"
RIVAL = "two readings fit equally"
LINE_BREAK = "line-break hyphen: the word is printed solid, so the hyphen would have to go too"
UNPRINTED = "the joined form is printed nowhere else"
NO_SIBLING = "no sibling prints the two words"

_MARK = re.compile(r"(?<=[a-z]{2}[.,;:!?])(?=[A-Z“‘])")  # "Damascus.Behold"
_HEAD = re.compile(r"^[^\W\d_]+")
_TAIL = re.compile(r"[^\W\d_]+[.,;:!?]$")


class Token(NamedTuple):
    lead: str  # opening punctuation
    core: str
    trail: str  # closing punctuation
    alpha: bool  # the core is letters only


def split_token(token: str) -> Token:
    core = token.lstrip(OPENING)
    bare = core.rstrip(CLOSING)
    return Token(token[: len(token) - len(core)], bare, core[len(bare) :], bare.isalpha())


def _attach(left: Token, right: Token) -> bool:
    """Could ``left`` and ``right`` be one word with a stray space between them?"""
    return left.alpha and right.alpha and not left.trail and not right.lead


def _space_kind(a: str, b: str) -> str | None:
    """Is the space between raw tokens ``a`` and ``b`` a stray one beside a hyphen ("sin-
    offering", "Ben -hadad") or inside a possessive ("father’ s", "woman ’s")?"""
    if (len(a) > 1 and a[-1] == "-" and a[-2].isalpha() and b[:1].isalpha()) or (
        len(b) > 1 and b[0] == "-" and b[1].isalpha() and a[-1:].isalpha()
    ):
        return "hyphen"
    possessive_s = split_token(b)
    if (
        len(a) > 1
        and a[-1] in APOSTROPHES
        and a[-2].isalpha()
        and possessive_s.core == "s"
        and not possessive_s.lead
    ) or (a[-1:].isalpha() and b[:1] in APOSTROPHES and b[1:2] == "s" and not b[2:3].isalpha()):
        return "apostrophe"
    return None


class Words:
    """One translation's verses as tokens, and the counts its evidence rules read."""

    def __init__(self, verses: Mapping[Ref, str]) -> None:
        cache: dict[str, tuple[Token, str]] = {}
        self.tokens: dict[Ref, list[Token]] = {}
        self.lower: dict[Ref, list[str]] = {}
        self.count: Counter[str] = Counter()
        self.pairs: Counter[tuple[str, str]] = Counter()
        for ref, text in verses.items():
            parsed: list[tuple[Token, str]] = []
            for raw in text.split(" "):
                hit = cache.get(raw)
                if hit is None:
                    token = split_token(raw)
                    hit = cache[raw] = (token, token.core.lower())
                parsed.append(hit)
            lower = [low for _, low in parsed]
            self.tokens[ref] = [token for token, _ in parsed]
            self.lower[ref] = lower
            self.count.update(lower)
            self.pairs.update(zip(lower, lower[1:], strict=False))
        del self.count[""]
        first = self._alone({w for w, n in self.count.items() if n >= COMMON})
        self.alone = self._alone({w for w, n in first.items() if n >= 2})
        self._pair_sets: dict[Ref, frozenset[tuple[str, str]]] = {}

    def _alone(self, known: set[str]) -> Counter[str]:
        """How often each word stands with no neighbour it joins into a ``known`` word."""
        alone: Counter[str] = Counter()
        for ref, tokens in self.tokens.items():
            lower = self.lower[ref]
            joined = [False] * len(tokens)
            for i in range(len(tokens) - 1):
                word = lower[i] + lower[i + 1]
                if (
                    word in known
                    and _attach(tokens[i], tokens[i + 1])
                    and self.pairs[(lower[i], lower[i + 1])] <= self.count[word]
                ):  # not a phrase the translation prefers ("the man" beside a glued "theMan")
                    joined[i] = joined[i + 1] = True
            alone.update(
                w for w, j, t in zip(lower, joined, tokens, strict=True) if t.alpha and not j
            )
        return alone

    def is_word(self, piece: str) -> bool:
        return piece in LETTER_WORDS if len(piece) == 1 else self.alone[piece.lower()] >= 2

    def common(self, word: str) -> bool:
        return word in ("a", "i", "o") or (len(word) >= 2 and self.alone[word] >= COMMON)

    def pair_set(self, ref: Ref) -> frozenset[tuple[str, str]]:
        found = self._pair_sets.get(ref)
        if found is None:
            lower = self.lower[ref]
            found = self._pair_sets[ref] = frozenset(zip(lower, lower[1:], strict=False))
        return found


class Corpus:
    """Every English translation's words: each one's verses are evidence for the others'."""

    def __init__(self, texts: Mapping[str, Mapping[Ref, str]]) -> None:
        self.texts = texts
        self.words = {code: Words(verses) for code, verses in texts.items()}
        self.somewhere: Counter[str] = Counter()  # translations a word stands alone in
        self.printed: Counter[str] = Counter()  # tokens printed, all translations together
        for words in self.words.values():
            self.somewhere.update(words.alone.keys())
            self.printed.update(words.count)

    def siblings(self, code: str, ref: Ref) -> list[str]:
        return [c for c, w in self.words.items() if c != code and ref in w.lower]


@dataclass(frozen=True, slots=True)
class Edit:
    token: int  # the first token the edit touches
    size: int  # tokens joined into one (> 1), or 1: a token split in two
    cut: int = 0  # for a split, where in the token the space goes


@dataclass(frozen=True, slots=True)
class Change:
    code: str
    ref: Ref
    kind: str  # split | hyphen | apostrophe | glued | punctuation
    offset: int  # character offset of the edited span in the verse as it stood
    before: str  # the span with a word of context each side, as printed
    after: str  # the same span repaired
    count: int  # how often the repaired word (or two-word phrase) stands in the translation
    siblings: int  # sibling verses that print it
    edit: Edit


@dataclass(frozen=True, slots=True)
class Left:
    code: str
    ref: Ref
    kind: str
    span: str  # as printed
    reason: str


@dataclass(slots=True)
class Findings:
    changes: list[Change]
    left: list[Left]


class _Run(NamedTuple):
    start: int
    size: int
    joined: str
    fragments: tuple[int, ...]  # token positions within the run that are no word
    siblings: int


class _Verse:
    """One verse of one translation, with what the evidence rules need about it."""

    def __init__(self, corpus: Corpus, code: str, ref: Ref) -> None:
        self.corpus, self.code, self.ref = corpus, code, ref
        self.words = corpus.words[code]
        self.raw = corpus.texts[code][ref].split(" ")
        self.tokens = self.words.tokens[ref]
        self.lower = self.words.lower[ref]
        codes = corpus.siblings(code, ref)
        self.siblings = [corpus.words[c] for c in codes]
        self.sibling_texts = [corpus.texts[c][ref].lower() for c in codes]
        self.used: set[int] = set()
        self.changes: list[Change] = []
        self.left: list[Left] = []

    # -- evidence --------------------------------------------------------------------------

    def sibling_count(self, word: str) -> int:
        return sum(1 for s in self.siblings if word in s.lower[self.ref])

    def prints_pair(self, a: str, b: str) -> int:
        return sum(1 for s in self.siblings if (a, b) in s.pair_set(self.ref))

    def prints_run(self, start: int, size: int) -> bool:
        """Does a sibling print these pieces side by side, as this verse does?"""
        pieces = self.lower[start : start + size]
        return any(
            s.lower[self.ref][m : m + size] == pieces
            for s in self.siblings
            for m in range(len(s.lower[self.ref]) - size + 1)
        )

    def word_here(self, k: int, lo: int, hi: int) -> bool:
        """Is token ``k`` a word, judged within the run ``lo``..``hi`` (exclusive)?"""
        piece = self.tokens[k].core
        if self.words.is_word(piece):
            return True
        if len(piece) == 1:
            return False
        low = self.lower[k]
        left = self.lower[k - 1] if k > lo else None
        right = self.lower[k + 1] if k + 1 < hi else None
        for sibling in self.siblings:
            seq = sibling.lower[self.ref]
            for m, w in enumerate(seq):
                if w != low:
                    continue
                same_left = left is not None and m > 0 and seq[m - 1] == left
                same_right = right is not None and m + 1 < len(seq) and seq[m + 1] == right
                if not same_left and not same_right:
                    return True  # printed alone, not as the same split
        return False

    def nowhere_a_word(self, k: int) -> bool:
        piece = self.tokens[k].core
        if len(piece) == 1:
            return piece not in LETTER_WORDS
        return self.corpus.somewhere[piece.lower()] == 0

    # -- output ----------------------------------------------------------------------------

    def offset(self, token: int) -> int:
        return sum(len(t) + 1 for t in self.raw[:token])

    def change(self, kind: str, edit: Edit, count: int, siblings: int) -> None:
        lo, hi = max(0, edit.token - 1), min(len(self.raw), edit.token + edit.size + 1)
        before = " ".join(self.raw[lo:hi])
        middle = self.raw[edit.token : edit.token + edit.size]
        joined = edit.size > 1
        fixed = ["".join(middle)] if joined else [middle[0][: edit.cut], middle[0][edit.cut :]]
        after = " ".join(
            [*self.raw[lo : edit.token], *fixed, *self.raw[edit.token + edit.size : hi]]
        )
        start = self.offset(edit.token) + (edit.cut if edit.size == 1 else 0)
        self.changes.append(
            Change(self.code, self.ref, kind, start, before, after, count, siblings, edit)
        )
        self.used.update(range(edit.token, edit.token + edit.size))

    def leave(self, kind: str, span: str, reason: str) -> None:
        self.left.append(Left(self.code, self.ref, kind, span, reason))

    # -- glued -----------------------------------------------------------------------------

    def glued(self) -> None:
        words = self.words
        for i, token in enumerate(self.tokens):
            core, low = token.core, self.lower[i]
            if words.count[low] > 2 or len(core) < 4 or not token.alpha:
                continue
            capital = any(c.isupper() for c in core[1:])  # "theLord", "Iwill": never one word
            if words.count[low] > 1 and not capital:
                continue
            if self.corpus.printed[low] != words.count[low] or self.fragment(i):
                continue  # printed in another translation, or half of a broken word
            cuts = [
                k for k in range(1, len(low)) if words.common(low[:k]) and words.common(low[k:])
            ]
            if len(cuts) != 1 or not words.pairs[(low[: cuts[0]], low[cuts[0] :])]:
                continue
            a, b = low[: cuts[0]], low[cuts[0] :]
            hyphenated = f"{a}-{b}"
            if a == "a" or words.count[hyphenated] or self.sibling_count(hyphenated):
                self.leave("glued", core, COMPOUND)  # "awork", "mercyseat" beside "mercy-seat"
                continue
            siblings = self.prints_pair(a, b)
            if siblings:
                self.change(
                    "glued", Edit(i, 1, len(token.lead) + cuts[0]), words.pairs[(a, b)], siblings
                )
            else:
                self.leave("glued", core, NO_SIBLING)
        for i, raw in enumerate(self.raw):
            mark = _MARK.search(raw)
            if mark is None or i in self.used:
                continue
            head, tail = _TAIL.search(raw[: mark.start()]), _HEAD.search(raw[mark.start() :])
            if head is None or tail is None:
                continue
            spaced = re.compile(
                r"(?<![^\W\d_])" + re.escape(head.group(0).lower() + " " + tail.group(0).lower())
            )
            siblings = sum(1 for text in self.sibling_texts if spaced.search(text))
            if siblings:
                self.change("punctuation", Edit(i, 1, mark.start()), 0, siblings)
            else:
                self.leave("punctuation", raw, NO_SIBLING)

    def fragment(self, i: int) -> bool:
        """Does token ``i`` join a neighbour into a word, i.e. is it half of a broken word?"""
        tokens, lower, alone = self.tokens, self.lower, self.words.alone
        if i > 0 and _attach(tokens[i - 1], tokens[i]) and alone[lower[i - 1] + lower[i]] >= 2:
            return True
        n = len(tokens)
        return (
            i + 1 < n and _attach(tokens[i], tokens[i + 1]) and alone[lower[i] + lower[i + 1]] >= 2
        )

    # -- broken ----------------------------------------------------------------------------

    def runs(self) -> tuple[list[_Run], list[_Run]]:
        """Candidate runs: those with a fragment, and those whose pieces are all words."""
        tokens, lower, words, used = self.tokens, self.lower, self.words, self.used
        alone = words.alone
        links = [_attach(a, b) for a, b in zip(tokens, tokens[1:], strict=False)]
        broken: list[_Run] = []
        whole: list[_Run] = []
        for i, link in enumerate(links):
            if not link:
                continue
            for size in (3, 2):
                if size == 3 and (i + 1 >= len(links) or not links[i + 1]):
                    continue
                joined = "".join(lower[i : i + size])
                if alone[joined] < 2:
                    continue
                if used and any(k in used for k in range(i, i + size)):
                    continue
                if any(
                    words.pairs[(lower[k], lower[k + 1])] > words.count[joined]
                    for k in range(i, i + size - 1)
                ):
                    continue  # a phrase the translation prefers ("money changers")
                fragments = tuple(
                    k for k in range(i, i + size) if not self.word_here(k, i, i + size)
                )
                run = _Run(i, size, joined, fragments, self.sibling_count(joined))
                (broken if fragments else whole).append(run)
        return broken, whole

    def split(self) -> None:
        broken, whole = self.runs()
        for cluster in _clusters(broken):
            chosen = self.resolve(cluster)
            if chosen is None:
                lo = min(r.start for r in cluster)
                hi = max(r.start + r.size for r in cluster)
                self.leave("split", " ".join(self.raw[lo:hi]), RIVAL)
                continue
            for run in chosen:
                self.judge(run)
        for run in whole:
            pieces = self.raw[run.start : run.start + run.size]
            if run.siblings >= 2 and not self.prints_run(run.start, run.size):
                self.leave("split", " ".join(pieces), BOTH_WORDS)

    def judge(self, run: _Run) -> None:
        span = range(run.start, run.start + run.size)
        pieces = [self.tokens[k].core for k in span]
        words = self.words
        printed = " ".join(self.raw[run.start : run.start + run.size])
        if any(p in LETTER_WORDS for p in pieces) and any(
            len(p) >= 3 and self.corpus.somewhere[p.lower()] > 0
            for p in pieces
            if p not in LETTER_WORDS
        ):
            self.leave("split", printed, ONE_LETTER)
        elif any(p in LETTER_WORDS for p in pieces) and not self.fits_context(run):
            self.leave("split", printed, ONE_LETTER_CONTEXT)
        elif run.siblings or (
            words.alone[run.joined] >= 3 and any(self.nowhere_a_word(k) for k in run.fragments)
        ):
            self.change("split", Edit(run.start, run.size), words.alone[run.joined], run.siblings)
        else:
            self.leave("split", printed, THIN)

    def fits_context(self, run: _Run) -> bool:
        """With a one-letter word as a piece ("a lone witness"), is the joined word attested here?

        The translation must print the joined word after this verse's left neighbour or before
        its right one elsewhere (both, when no sibling prints it in this verse), and the piece
        must not precede the next word more often elsewhere than the joined word does
        ("lone witness" beside a never-printed "alone witness")."""
        pairs, lower = self.words.pairs, self.lower
        end = run.start + run.size
        right = lower[end] if end < len(lower) else None
        if right is not None and pairs[(lower[end - 1], right)] - 1 > pairs[(run.joined, right)]:
            return False
        before = run.start > 0 and pairs[(lower[run.start - 1], run.joined)] > 0
        after = right is not None and pairs[(run.joined, right)] > 0
        return (before or after) if run.siblings else (before and after)

    def resolve(self, cluster: list[_Run]) -> list[_Run] | None:
        """The best reading of overlapping runs, or None when two readings tie."""
        if len(cluster) == 1:
            return cluster
        lo = min(r.start for r in cluster)
        hi = max(r.start + r.size for r in cluster)
        scored: list[tuple[tuple[int, int, float], list[_Run]]] = []
        for n in range(1, len(cluster) + 1):
            for combo in combinations(cluster, n):
                spans = [set(range(r.start, r.start + r.size)) for r in combo]
                if any(a & b for a, b in combinations(spans, 2)):
                    continue
                scored.append((self.score(list(combo), lo, hi), list(combo)))
        scored.sort(key=lambda s: s[0])
        best = scored[0]
        if len(scored) > 1:
            other = scored[1][0]
            if other[:2] == best[0][:2] and abs(other[2] - best[0][2]) < TIE:
                return None
        return best[1]

    def score(self, combo: list[_Run], lo: int, hi: int) -> tuple[int, int, float]:
        """(fragments left, -word pairs the siblings print, -bigram score): lower is better."""
        starts = {r.start: r for r in combo}
        seq: list[str] = [self.lower[lo - 1]] if lo > 0 else []
        fragments = 0
        k = lo
        while k < hi:
            if k in starts:
                seq.append(starts[k].joined)
                k += starts[k].size
            else:
                seq.append(self.lower[k])
                fragments += not self.word_here(k, lo, hi)
                k += 1
        if hi < len(self.lower):
            seq.append(self.lower[hi])
        pairs = list(zip(seq, seq[1:], strict=False))
        printed = sum(1 for a, b in pairs if self.prints_pair(a, b))
        bigrams = sum(math.log1p(self.words.pairs[(a, b)]) for a, b in pairs)
        return fragments, -printed, -bigrams

    def hyphens_and_apostrophes(self) -> None:
        raw, words = self.raw, self.words
        for i in range(len(raw) - 1):
            if i in self.used or i + 1 in self.used:
                continue
            a, b = raw[i], raw[i + 1]
            kind = _space_kind(a, b)
            if kind is None:
                continue
            joined = split_token(a + b).core.lower()
            forms = {joined, joined.replace("’", "'"), joined.replace("'", "’")}
            count = max(words.count[f] for f in forms)
            siblings = sum(1 for s in self.siblings if forms & set(s.lower[self.ref]))
            if count or siblings:
                self.change(kind, Edit(i, 2), count, siblings)
                continue
            solid = ""
            if kind == "hyphen":
                solid = split_token(a[:-1] + b if a.endswith("-") else a + b[1:]).core.lower()
            reason = (
                LINE_BREAK
                if solid and (words.count[solid] or self.sibling_count(solid))
                else UNPRINTED
            )
            self.leave(kind, f"{a} {b}", reason)


def _clusters(runs: Sequence[_Run]) -> list[list[_Run]]:
    """Group runs that share a token."""
    clusters: list[list[_Run]] = []
    end = -1
    for run in sorted(runs, key=lambda r: (r.start, -r.size)):
        if clusters and run.start < end:
            clusters[-1].append(run)
            end = max(end, run.start + run.size)
        else:
            clusters.append([run])
            end = run.start + run.size
    return clusters


def detect(corpus: Corpus, targets: Iterable[str] | None = None, kinds: str = "all") -> Findings:
    """Every repair the evidence supports in ``targets`` (default: all), and every case left."""
    wanted = KINDS[kinds]
    found = Findings([], [])
    for code in targets if targets is not None else corpus.words:
        for ref in corpus.texts[code]:
            verse = _Verse(corpus, code, ref)
            if "glued" in wanted:
                verse.glued()
            if "split" in wanted:
                verse.split()
            if "hyphen" in wanted or "apostrophe" in wanted:
                verse.hyphens_and_apostrophes()
            found.changes.extend(c for c in verse.changes if c.kind in wanted)
            found.left.extend(item for item in verse.left if item.kind in wanted)
    return found


def apply_changes(text: str, changes: Sequence[Change]) -> str:
    """``text`` with ``changes`` made; asserts that only spaces were removed or inserted."""
    raw = text.split(" ")
    out: list[str] = []
    at = 0
    for edit in sorted((c.edit for c in changes), key=lambda e: e.token):
        if edit.token < at:
            raise ValueError(f"overlapping edits in {text!r}")
        out.extend(raw[at : edit.token])
        if edit.size > 1:
            out.append("".join(raw[edit.token : edit.token + edit.size]))
        else:
            token = raw[edit.token]
            out.extend([token[: edit.cut], token[edit.cut :]])
        at = edit.token + edit.size
    out.extend(raw[at:])
    fixed = " ".join(out)
    removed = sum(c.edit.size - 1 for c in changes)
    inserted = sum(1 for c in changes if c.edit.size == 1)
    if (
        fixed.replace(" ", "") != text.replace(" ", "")
        or fixed.count(" ") != text.count(" ") - removed + inserted
    ):
        raise AssertionError(f"a repair changed more than spaces: {text!r} -> {fixed!r}")
    return fixed


def repair(
    texts: dict[str, dict[Ref, str]], targets: Iterable[str] | None = None, kinds: str = "all"
) -> Findings:
    """Apply every supported repair to ``targets`` in place, until none is left."""
    codes = list(targets) if targets is not None else list(texts)
    applied: list[Change] = []
    for _ in range(8):
        found = detect(Corpus(texts), codes, kinds)
        if not found.changes:
            return Findings(applied, found.left)
        by_verse: dict[tuple[str, Ref], list[Change]] = defaultdict(list)
        for change in found.changes:
            by_verse[(change.code, change.ref)].append(change)
        for (code, ref), changes in by_verse.items():
            texts[code][ref] = apply_changes(texts[code][ref], changes)
        applied.extend(found.changes)
    raise RuntimeError("repairs did not settle in 8 rounds")


# A lone letter other than a/A/I/O between spaces or before a mark: the literal leading space
# keeps the scan fast. Verses are joined with "\n " so each starts after a space.
_LONE = re.compile(r" [b-zB-HJ-NP-Z][ ,.;:!?\n]")


def quick_check(verses: Mapping[Ref, str]) -> list[tuple[Ref, str]]:
    """The fast guard, for one translation: the two commonest faults ``detect`` repairs.

    A lone letter (not a/A/I/O) that joins a neighbour into a word the translation prints at
    least ``COMMON`` times ("t he", "an d", about a third of all breaks), and a stray space
    beside a hyphen in a compound the translation prints whole ("sin- offering"). Under a
    second for the whole corpus, where ``detect`` takes a minute; ``detect`` is the full guard.
    """
    refs = list(verses)
    text = " " + "\n ".join(verses.values())
    lower = text.lower()
    counted: dict[str, int] = {}

    def common(word: str) -> bool:  # space-delimited occurrences: enough to prove COMMON
        if word not in counted:
            counted[word] = lower.count(f" {word} ")
        return counted[word] >= COMMON

    found: list[tuple[Ref, str]] = []
    hyphenated = [ref for ref, verse in verses.items() if "- " in verse or " -" in verse]
    if hyphenated:
        compounds = {
            core
            for verse in verses.values()
            if "-" in verse
            for token in verse.lower().split()
            if "-" in (core := split_token(token).core) and core[0] != "-" and core[-1] != "-"
        }
        for ref in hyphenated:
            raw = verses[ref].split(" ")
            for a, b in zip(raw, raw[1:], strict=False):
                if _space_kind(a, b) == "hyphen" and split_token(a + b).core.lower() in compounds:
                    found.append((ref, f"{a} {b}"))

    starts: list[int] = []
    at = 0
    for verse in verses.values():
        starts.append(at)
        at += len(verse) + 2
    lone = {refs[bisect_right(starts, m.start()) - 1] for m in _LONE.finditer(text)}
    for ref in sorted(lone):
        raw = verses[ref].split(" ")
        tokens = [split_token(t) for t in raw]
        for i, token in enumerate(tokens):
            if len(token.core) != 1 or token.core in LETTER_WORDS or not token.alpha:
                continue
            for a, b in ((i - 1, i), (i, i + 1)):
                if (
                    a >= 0
                    and b < len(tokens)
                    and tokens[a if b == i else b].core not in LETTER_WORDS  # "a s": detect's call
                    and _attach(tokens[a], tokens[b])
                    and common((tokens[a].core + tokens[b].core).lower())
                ):
                    found.append((ref, f"{raw[a]} {raw[b]}"))
    return found


# -- files ---------------------------------------------------------------------------------


class TranslationFile:
    """A translation JSON file, its verses by ``Ref``, and whether it may be changed."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.original = path.read_text(encoding="utf-8")
        self.data: dict[str, Any] = json.loads(self.original)
        self.code: str = self.data["code"]
        self.english = str(self.data.get("language", "")).lower().startswith("en")
        self.verses: dict[Ref, str] = {}
        self.labels: dict[Ref, str] = {}
        self._entries: dict[Ref, dict[str, Any]] = {}
        anchored = (path.parent / "notes" / f"{self.code}.json").exists()
        for book in self.data["books"]:
            for chapter in book["chapters"]:
                footnotes: list[dict[str, Any]] = chapter.get("footnotes") or []
                anchored = anchored or any(n.get("char_offset") is not None for n in footnotes)
                for verse in chapter["verses"]:
                    ref = (int(book["order_index"]), int(chapter["number"]), int(verse["number"]))
                    self.verses[ref] = verse["text"]
                    self.labels[ref] = (
                        f"{book['abbreviation']} {chapter['number']}:{verse['number']}"
                    )
                    self._entries[ref] = verse
        self.anchored = anchored

    def round_trips(self) -> bool:
        return self.dump() == self.original

    def dump(self) -> str:
        text = json.dumps(self.data, indent=2, ensure_ascii=False)
        return text + "\n" if self.original.endswith("\n") else text

    def write(self, verses: Mapping[Ref, str]) -> None:
        for ref, text in verses.items():
            self._entries[ref]["text"] = text
        self.path.write_text(self.dump(), encoding="utf-8")


def _load(folder: Path) -> list[TranslationFile]:
    return [TranslationFile(p) for p in sorted(folder.glob("*.json"))]


MANIFEST_FIELDS = (
    "translation",
    "reference",
    "offset",
    "kind",
    "before",
    "after",
    "count",
    "siblings",
)


def _write_manifest(
    folder: Path,
    changes: Sequence[Change],
    left: Sequence[Left],
    pending: int,
    labels: Mapping[str, Mapping[Ref, str]],
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / "broken_words_manifest.csv"
    new = not csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        if new:
            writer.writerow(MANIFEST_FIELDS)
        for c in sorted(changes, key=lambda c: (c.code, c.ref, c.offset)):
            writer.writerow(
                [
                    c.code,
                    labels[c.code][c.ref],
                    c.offset,
                    c.kind,
                    c.before,
                    c.after,
                    c.count,
                    c.siblings,
                ]
            )
    with csv_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    per: dict[str, Counter[str]] = defaultdict(Counter)
    verses: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        per[row["translation"]][row["kind"]] += 1
        verses[row["translation"]].add(row["reference"])
    kinds = KINDS["all"]
    md = [
        "# Broken- and glued-word cleanup manifest",
        "",
        "Written by [fix_broken_words.py](fix_broken_words.py). Every change is a row of "
        "[broken_words_manifest.csv](broken_words_manifest.csv): translation, reference, the "
        "character offset of the edit in the verse as it stood, kind, the text before and after "
        "(with a word of context each side), and the evidence — how often the repaired word (or, "
        "for a glued pair, the two-word phrase) stands in that translation, and how many "
        "sibling verses print it.",
        "",
        f"**{len(rows)} changes** in {sum(len(v) for v in verses.values())} verses. "
        "Kinds: `split` — a word split by a stray space; `hyphen` — a stray space beside a hyphen; "
        "`apostrophe` — one inside a possessive; `glued` — two words run together; `punctuation` — "
        "no space after a sentence's mark.",
        "",
        "| Translation | " + " | ".join(kinds) + " | Changes | Verses |",
        "| --- | " + " | ".join("---:" for _ in kinds) + " | ---: | ---: |",
    ]
    for code in sorted(per):
        cells = " | ".join(f"{per[code][k]:,}" for k in kinds)
        md.append(f"| {code} | {cells} | {sum(per[code].values()):,} | {len(verses[code]):,} |")
    if pending:
        md += ["", f"**Not yet applied:** {pending} further changes of the kinds this run skipped."]
    reasons = Counter(item.reason for item in left)
    md += ["", f"## Left alone ({len(left)})", "", "| Reason | Cases |", "| --- | ---: |"]
    md += [f"| {reason} | {n} |" for reason, n in reasons.most_common()]
    md += [
        "",
        "| Translation | Reference | Kind | As printed | Reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in sorted(left, key=lambda x: (x.code, x.ref, x.span)):
        span = item.span.replace("|", "\\|")
        ref = labels[item.code][item.ref]
        md.append(f"| {item.code} | {ref} | {item.kind} | {span} | {item.reason} |")
    (folder / "broken_words_manifest.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def _summary(found: Findings, title: str) -> list[str]:
    per: dict[str, Counter[str]] = defaultdict(Counter)
    for c in found.changes:
        per[c.code][c.kind] += 1
    left = Counter(item.code for item in found.left)
    lines = [title]
    for code in sorted(set(per) | set(left)):
        kinds = ", ".join(f"{k} {per[code][k]}" for k in KINDS["all"] if per[code][k]) or "none"
        total = sum(per[code].values())
        lines.append(f"  {code:6} {total:6} changes ({kinds}); {left[code]} left alone")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--data-dir", type=Path, default=Path("data/translations"))
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        action="append",
        default=[],
        help="more siblings, never changed",
    )
    parser.add_argument(
        "--only", default="", help="comma-separated codes to change (default: every one allowed)"
    )
    parser.add_argument("--kinds", choices=sorted(KINDS), default="all")
    parser.add_argument("--manifest-dir", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--dry-run", action="store_true", help="detect and count; write nothing")
    parser.add_argument(
        "--list", action="store_true", help="print every change and every case left alone"
    )
    args = parser.parse_args(argv)

    files = _load(args.data_dir)
    if not files:
        print(f"No translation JSON found under {args.data_dir}", file=sys.stderr)
        return 1
    evidence = [f for folder in args.evidence_dir for f in _load(folder)]
    english = [f for f in [*files, *evidence] if f.english]
    seen = Counter(f.code for f in english)
    if any(n > 1 for n in seen.values()):
        twice = ", ".join(sorted(c for c, n in seen.items() if n > 1))
        print(f"The same translation code appears twice: {twice}", file=sys.stderr)
        return 1
    texts = {f.code: dict(f.verses) for f in english}
    labels = {f.code: f.labels for f in english}
    only = {c.strip() for c in args.only.split(",") if c.strip()}
    candidates = [f for f in files if f.english and (not only or f.code in only)]
    for f in files:
        if not f.english:
            print(f"  {f.code}: not English — neither changed nor used as evidence")
    refused = [f for f in candidates if f.anchored]
    for f in refused:
        print(f"  {f.code}: has character-anchored notes — never changed")
    targets = [f for f in candidates if not f.anchored]

    if args.dry_run:
        found = detect(Corpus(texts), [f.code for f in candidates], args.kinds)
        print("\n".join(_summary(found, f"DRY-RUN — one pass, nothing written ({args.kinds}):")))
        if refused:
            print(
                "  ("
                + ", ".join(f.code for f in refused)
                + " counted only: they are never changed)"
            )
        if args.list:
            _print_all(found, labels)
        return 0

    for f in targets:
        if not f.round_trips():
            print(
                f"{f.path}: does not round-trip through json.dumps — refusing to write it",
                file=sys.stderr,
            )
            return 1
    found = repair(texts, [f.code for f in targets], args.kinds)
    if not found.changes:
        print("Nothing to repair: no file or manifest written.")
        return 0
    changed = {c.code for c in found.changes}
    for f in targets:
        if f.code in changed:
            f.write({ref: texts[f.code][ref] for ref in f.verses})
    final = detect(Corpus(texts), [f.code for f in targets], "all")
    _write_manifest(args.manifest_dir, found.changes, final.left, len(final.changes), labels)
    print("\n".join(_summary(found, f"Applied ({args.kinds}):")))
    print(f"Manifest: {args.manifest_dir / 'broken_words_manifest.md'}")
    if args.list:
        _print_all(found, labels)
    return 0


def _print_all(found: Findings, labels: Mapping[str, Mapping[Ref, str]]) -> None:
    for c in found.changes:
        print(
            "\t".join(
                [
                    "CHANGE",
                    c.code,
                    labels[c.code][c.ref],
                    c.kind,
                    c.before,
                    c.after,
                    str(c.count),
                    str(c.siblings),
                ]
            )
        )
    for item in found.left:
        print(
            "\t".join(
                ["LEFT", item.code, labels[item.code][item.ref], item.kind, item.span, item.reason]
            )
        )


if __name__ == "__main__":
    sys.exit(main())
