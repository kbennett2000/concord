"""The EPUB's feature articles — a witness for the PDF's article text, never a source (V8-S3a).

Each feature's section opens with its index header in bold capitals (its outline title, upper
case) and runs to the next "… INDEX" header. Inside, the articles come in the PDF's order:

- Men, Women, and God: the title in bold, then the passage, then the text;
- Someone You Should Know: "…:" (the label) and the name in bold, the passage, the text;
- Personal Gold: the label in bold, "from" and the author in bold, the passage, the title in
  bold capitals, the text.

So an article is found by its heading, in order, and keyed like the PDF's (feature, printed
passage, occurrence). Its text runs from after the heading (and passage) to the next
article's label or heading. A heading found only by resemblance, or a passage that doesn't
read as the PDF's, marks the article damaged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from emb_convert.articles import MWG, PG, SYSK, Article, Feature
from emb_convert.epub import BREAK
from emb_convert.epub_notes import read_runs

Key = tuple[str, int, int]

_INDEX = re.compile(r"^[A-Z][A-Z,’'. ]+ INDEX$")
_WS = re.compile(r"\s+")
_FLAT = re.compile(r"[\s–—\-]")
SIMILAR = 0.8


@dataclass(slots=True)
class EpubArticles:
    texts: dict[Key, str] = field(default_factory=dict[Key, str])
    damaged: set[Key] = field(default_factory=set[Key])
    missing: list[Key] = field(default_factory=list[Key])


def _clean(text: str) -> str:
    return _WS.sub(" ", text.replace(BREAK, " ")).strip()


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def _like(a: str, b: str) -> tuple[bool, bool]:
    """(the same heading?, only by resemblance?)"""
    if _key(a) == _key(b):
        return True, False
    return SequenceMatcher(None, _key(a), _key(b)).ratio() >= SIMILAR, True


def parse_epub_articles(path: Path, articles: list[tuple[Key, Article]]) -> EpubArticles:
    runs = [(text, bold) for text, bold in read_runs(path)]
    found = EpubArticles()
    for feature in (MWG, SYSK, PG):
        mine = [(key, a) for key, a in articles if a.feature is feature]
        section = _section(runs, feature)
        if section is None:
            found.missing += [key for key, _ in mine]
            continue
        _read(runs, section, feature, mine, found)
    return found


def _section(runs: list[tuple[str, bool]], feature: Feature) -> tuple[int, int] | None:
    header = feature.outline.upper()
    start = next((n for n, (t, bold) in enumerate(runs) if bold and _clean(t) == header), None)
    if start is None:
        return None
    end = next(
        (n for n in range(start + 1, len(runs)) if runs[n][1] and _INDEX.match(_clean(runs[n][0]))),
        len(runs),
    )
    return start + 1, end


@dataclass(slots=True)
class _Place:
    key: Key
    article: Article
    cut: tuple[int, int]  # (run, offset): where the text before this article ends
    body: tuple[int, int]  # (run, offset): where its text starts (after the heading)
    damaged: bool


def _read(
    runs: list[tuple[str, bool]],
    section: tuple[int, int],
    feature: Feature,
    mine: list[tuple[Key, Article]],
    found: EpubArticles,
) -> None:
    at, end = section
    places: list[_Place] = []
    label = feature.label.lower()
    for key, article in mine:
        place = _find(runs, at, end, feature, article, key, label)
        if place is None:
            found.missing.append(key)
            continue
        places.append(place)
        at = place.body[0]
    for k, place in enumerate(places):
        stop = places[k + 1].cut if k + 1 < len(places) else (end, 0)
        text = _clean(_slice(runs, place.body, stop))
        damaged = place.damaged
        if place.article.feature is not PG:
            text, read = _past_reference(text, place.article.reference)
            damaged = damaged or not read
        found.texts[place.key] = text
        if damaged:
            found.damaged.add(place.key)


def _slice(runs: list[tuple[str, bool]], start: tuple[int, int], stop: tuple[int, int]) -> str:
    """The runs' text from ``start`` up to ``stop`` ((run, offset) each)."""
    if start[0] == stop[0]:
        return runs[start[0]][0][start[1] : stop[1]]
    parts = [runs[start[0]][0][start[1] :]]
    parts += [runs[n][0] for n in range(start[0] + 1, min(stop[0], len(runs)))]
    if stop[0] < len(runs):
        parts.append(runs[stop[0]][0][: stop[1]])
    return "".join(parts)


def _find(
    runs: list[tuple[str, bool]],
    at: int,
    end: int,
    feature: Feature,
    article: Article,
    key: Key,
    label: str,
) -> _Place | None:
    for n in range(at, end):
        text, bold = runs[n]
        if feature is PG:
            if not bold or not _clean(text).lower().startswith("from "):
                continue
            title = next((k for k in range(n + 1, end) if runs[k][1]), None)
            if title is None:
                return None
            same, loose = _like(runs[title][0], article.printed)
            if not same:
                continue
            labelled = next(
                (
                    k
                    for k in range(n - 1, max(at, n - 4) - 1, -1)
                    if _clean(runs[k][0]).lower() == label
                ),
                n,
            )
            return _Place(key, article, (labelled, 0), (title + 1, 0), loose)
        if bold:
            same, loose = _like(text, article.printed)
            if not same:
                continue
            cut = (n, 0)
            if feature is SYSK:
                cut = _label_before(runs, n, at, label) or cut
                loose = loose or cut == (n, 0)
            return _Place(key, article, cut, (n + 1, 0), loose)
        if feature is SYSK:  # a heading the EPUB set in plain text, past a scrap
            plain = text.lower()
            where = plain.find(label)
            if where == -1:
                continue
            name = re.search(re.escape(article.printed.lower()), plain[where:])
            if name is None:
                continue
            return _Place(key, article, (n, where), (n, where + name.end()), True)
    return None


def _label_before(
    runs: list[tuple[str, bool]], n: int, start: int, label: str
) -> tuple[int, int] | None:
    """Where "label:" stands just before run ``n`` (the run and the offset it starts at)."""
    for k in range(n - 1, max(start, n - 4) - 1, -1):
        found = runs[k][0].lower().rfind(label)
        if found != -1:
            return k, found
    return None


def _past_reference(text: str, reference: str) -> tuple[str, bool]:
    """``text`` past the printed passage it opens with (spaces and dashes aside), and whether
    the passage read as the PDF's."""
    want = _FLAT.sub("", reference)
    k = 0
    for i, c in enumerate(text):
        if k == len(want):
            return text[i:].strip(), True
        if _FLAT.match(c):
            continue
        if c != want[k]:
            return text, False
        k += 1
    return ("", True) if k == len(want) else (text, False)
