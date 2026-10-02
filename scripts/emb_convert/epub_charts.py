"""The EPUB as a witness for the charts (V8-S4b).

The EPUB's images were re-encoded at a smaller size, so they can't witness a chart's bytes. They
can witness where each chart stands: the EPUB reader notes the verse open at every image it
meets (``EpubBible.images``), and a chart is there when one of the EPUB's large images stands
after the same verse with the same shape. The EPUB's own Charts Index witnesses each chart's
title and reference. Nothing here holds book text.
"""

from __future__ import annotations

import html
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from bible_core.assets import ImageError, image_header

from emb_convert.charts import Chart
from emb_convert.epub import parse_epub, spine_documents
from emb_convert.layout import canonical_books

INDEX_HEADER = "CHARTS INDEX"
RATIO_TOLERANCE = 0.015
# A chart or a full page; the EPUB's callout icons, banners and introduction figures are smaller.
LARGE = (400, 300)

_TAG = re.compile(r"<[^>]+>")
_SCRAP = re.compile(r"[<>=]")  # what's left of markup the conversion broke
_NEXT_INDEX = re.compile(r"\b[A-Z][A-Z’' ]{3,} INDEX\b")
_ENTRY = re.compile(r"\s*([^()]+?)\s*\(([^()]*\d[^()]*)\)")

Spot = tuple[str, int, int]  # book, chapter, the verse a chart follows


@dataclass(slots=True)
class ChartsCross:
    rows: list[tuple[str, str, str, str]] = field(default_factory=list[tuple[str, str, str, str]])
    index: Counter[str] = field(default_factory=Counter[str])
    images: Counter[str] = field(default_factory=Counter[str])
    entries: int = 0  # the EPUB index's entries
    large: int = 0  # the EPUB's large images placed in a book's chapters
    elsewhere: list[str] = field(default_factory=list[str])  # large images at no chart's spot

    @property
    def open(self) -> int:
        return self.index["open"]


def _key(text: str) -> str:
    """A title or reference as compared: quotes, dashes and spacing folded."""
    text = text.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    return " ".join(text.split())


def epub_index(archive: zipfile.ZipFile) -> list[tuple[str, str]]:
    """The EPUB's Charts Index: (title, reference) in its order."""
    for name in spine_documents(archive):
        page = archive.read(name).decode("utf-8", "replace")
        at = page.find(INDEX_HEADER)
        if at < 0:
            continue
        text = html.unescape(_TAG.sub("", page[at + len(INDEX_HEADER) :]))
        end = _NEXT_INDEX.search(text)
        return [
            (_key(title), _key(reference))
            for title, reference in _ENTRY.findall(text[: end.start() if end else None])
        ]
    return []


def _shape(data: bytes) -> float | None:
    """An image's width over its height; trailing zero padding after a JPEG is tolerated."""
    try:
        _, width, height = image_header(data.rstrip(b"\x00"))
    except ImageError:
        return None
    if width < LARGE[0] or height < LARGE[1]:
        return None
    return width / height


def cross_check_epub_charts(
    charts: list[Chart],
    spots: dict[int, Spot],
    epub_path: Path,
    skeleton: dict[tuple[str, int], int],
) -> ChartsCross:
    """Each chart's index entry and placed image against the EPUB's (``spots``: chart number →
    the verse its image follows in the PDF)."""
    cross = ChartsCross()
    placed = parse_epub(epub_path, canonical_books(), skeleton).images
    large: dict[Spot, list[float]] = {}
    with zipfile.ZipFile(epub_path) as archive:
        entries = epub_index(archive)
        for book, chapter, verse, path in placed:
            try:
                shape = _shape(archive.read(path))
            except KeyError:
                continue
            if shape is not None:
                large.setdefault((book, chapter, verse), []).append(shape)
    cross.entries = len(entries)
    cross.large = sum(len(shapes) for shapes in large.values())
    by_reference = {reference: (title, reference) for title, reference in entries}
    for n, chart in enumerate(charts):
        title, reference = _key(chart.title), _key(chart.reference)
        entry = entries[n] if len(entries) == len(charts) else by_reference.get(reference)
        if entry == (title, reference):
            index = "agree"
        elif entry is not None and _SCRAP.search(" ".join(entry)):
            index = "visible EPUB damage"
        else:
            index = "open"
        spot = spots.get(chart.number)
        shapes = large.get(spot, []) if spot is not None else []
        ratio = chart.width / chart.height if chart.height else 0.0
        found = next((s for s in shapes if abs(s - ratio) <= RATIO_TOLERANCE), None)
        if found is not None:
            shapes.remove(found)
        image = "at the same place" if found is not None else "not in the EPUB"
        cross.index[index] += 1
        cross.images[image] += 1
        cross.rows.append((chart.key, chart.reference, index, image))
    cross.elsewhere = [
        f"{book} {chapter}:{verse}" for (book, chapter, verse), left in large.items() for _ in left
    ]
    return cross


def charts_tsv(cross: ChartsCross) -> str:
    rows = ["chart\treference\tindex\timage"]
    rows += ["\t".join(row) for row in cross.rows]
    return "\n".join(rows) + "\n"
