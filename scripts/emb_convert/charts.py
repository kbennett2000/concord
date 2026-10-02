"""EMB's charts (V8-S4b, docs/v8/SPEC.md §4.2, §4.4, ADR-0012).

A chart is a picture in the text: its words are inside the image, so the text layer has no title
for it. The book's Charts Index lists every chart in book order — a title linked to the chart's
page, then its passage in parentheses linked to the passage's page. ``find_charts`` reads the
index, claims each entry's image (on the page its title links to, or the next), reads the
image's bytes as the PDF stores them, and counts every other image in the PDF by kind. The text
pass records where each claimed image stands (``text.ChartImage``); ``place`` turns that into
the note's anchor, with S3a's rule. Nothing here holds book text: titles and references come
from the operator's PDF at run time.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from bible_core.assets import MAX_ASSET_BYTES, ImageError, image_header

from emb_convert.articles import parse_reference, sections
from emb_convert.layout import Layout
from emb_convert.lines import group_lines
from emb_convert.pdfxml import ImageItem, PdfDocument, TextItem
from emb_convert.study import Part
from emb_convert.text import ChartImage

INDEX_OUTLINE = "Charts Index"
LABEL = "Chart"
NOTE_TYPE = "chart"
CHART_HEIGHT = 200  # points on the page: a chart is 300+, an introduction figure under 100
ICON_WIDTH = 200  # points: a callout icon is 45 or 135, every other image the text column

_EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png"}
_ABBREVIATION = re.compile(r"^((?:[1-3] )?[A-Z][a-z]+)\.(?= )")

# The image census's kinds, in the summary's order.
CENSUS = (
    "chart",
    "callout icon",
    "introduction figure",
    "page of its own",
    "front matter",
    "feature region",
    "unclassified",
)


@dataclass(slots=True)
class Chart:
    """One Charts Index entry, the image it claims and, once placed, its passage."""

    number: int  # 1-based, the index's (the book's) order
    title: str
    reference: str  # as printed
    page: int  # where the title links: the chart's page, or the page before it
    reference_page: int | None  # where the reference links: its passage
    image: ImageItem | None = None
    data: bytes = b""
    media_type: str = ""
    width: int = 0
    height: int = 0

    @property
    def name(self) -> str:
        return f"chart-{self.number:02d}.{_EXTENSIONS.get(self.media_type, 'jpg')}"

    @property
    def key(self) -> str:
        return f"chart {self.number}"


@dataclass(slots=True)
class ChartRegion:
    charts: list[Chart] = field(default_factory=list[Chart])
    census: Counter[str] = field(default_factory=Counter[str])
    unclaimed: list[ImageItem] = field(default_factory=list[ImageItem])
    errors: list[str] = field(default_factory=list[str])

    @property
    def images(self) -> list[ImageItem]:
        return [c.image for c in self.charts if c.image is not None]


def _entries(items: list[TextItem]) -> list[Chart]:
    """The index's entries: blue title runs, a black "(", blue reference runs, a black ")".
    A run may wrap onto the next line — a reference broken after its dash joins up."""
    charts: list[Chart] = []
    title: list[tuple[str, int | None]] = []
    reference: list[tuple[str, int | None]] = []
    in_reference = False
    for line in group_lines(items):
        for n, item in enumerate(line.items):
            text = item.text if n else f"\n{item.text}"
            if item.blue:
                (reference if in_reference else title).append((text, item.link_page))
            elif "(" in item.text and not in_reference:
                in_reference = True
            elif ")" in item.text and in_reference:
                charts.append(
                    Chart(
                        number=len(charts) + 1,
                        title=" ".join("".join(t for t, _ in title).split()),
                        reference=re.sub(r"(?<=[-–])\s+|\s+(?=[-–])", "", _join(reference)),
                        page=next((p for _, p in title if p is not None), 0),
                        reference_page=next((p for _, p in reference if p is not None), None),
                    )
                )
                title, reference, in_reference = [], [], False
    return charts


def _join(runs: list[tuple[str, int | None]]) -> str:
    return " ".join("".join(t for t, _ in runs).split())


def _read(chart: Chart, image: ImageItem, errors: list[str]) -> None:
    chart.image = image
    try:
        chart.data = image.src.read_bytes()
        chart.media_type, chart.width, chart.height = image_header(chart.data)
    except (OSError, ImageError) as exc:
        errors.append(f"{chart.key}: its image on p{image.page} can't be read ({exc})")
        return
    if len(chart.data) > MAX_ASSET_BYTES:
        errors.append(f"{chart.key}: its image is {len(chart.data):,} bytes, over the limit")


def find_charts(doc: PdfDocument, layout: Layout) -> ChartRegion:
    """Read the Charts Index, claim each entry's image, and count every image by kind."""
    region = ChartRegion()
    section = next((s for s in sections(doc, layout) if s.outline == INDEX_OUTLINE), None)
    if section is None:
        region.errors.append(f"the outline has no {INDEX_OUTLINE!r}")
        return region
    items = [i for i in doc.items if section.start <= i.page < section.end and not i.bold]
    region.charts = _entries(items)
    text_pages = {i.page for i in doc.items if i.stripped}

    def in_text(image: ImageItem) -> bool:
        return layout.bible_start <= image.page < layout.notes_start

    large = [i for i in doc.images if in_text(i) and i.height >= CHART_HEIGHT]
    claimed: dict[int, Chart] = {}
    for chart in region.charts:
        near = [i for i in large if i.page == chart.page] or [
            i for i in large if i.page == chart.page + 1
        ]
        if len(near) != 1:
            region.errors.append(
                f"{chart.key}: {len(near)} chart-sized images on p{chart.page} or the next page"
            )
            continue
        if id(near[0]) in claimed:
            region.errors.append(f"{chart.key}: its image is {claimed[id(near[0])].key}'s too")
            continue
        claimed[id(near[0])] = chart
        _read(chart, near[0], region.errors)
    for image in doc.images:
        if id(image) in claimed:
            kind = "chart"
        elif image.page < layout.bible_start:
            kind = "front matter"
        elif not in_text(image):
            kind = "feature region"
        elif image.page not in text_pages:
            kind = "page of its own"
        elif image.width < ICON_WIDTH:
            kind = "callout icon"
        elif image.height < CHART_HEIGHT:
            kind = "introduction figure"
        else:
            kind = "unclassified"
            region.unclaimed.append(image)
        region.census[kind] += 1
    return region


# --- the passage and where the chart stands ----------------------------------------------


@dataclass(frozen=True, slots=True)
class Placed:
    """A chart's passage and its note's anchor."""

    book: str
    parts: list[Part]
    shape: str
    whole_chapter: bool  # a range printed in full that is the whole chapter
    chapter: int
    verse: int  # a number the verse text is stored under
    at_end: bool  # at the end of the verse (char_offset = its length), else at its start
    where: str  # closes its passage · inside it · after it · before it
    target: str  # the ref: target for the whole printed passage


def shape(printed: str, part: Part) -> str:
    """As the spec counts the printed form: whole chapters · cross-chapter · verse · range."""
    if ":" not in printed:
        return "whole chapters"
    if part.start_chapter != part.end_chapter:
        return "cross-chapter"
    if part.start_verse == part.end_verse:
        return "verse"
    return "range"


def place(
    chart: Chart,
    record: ChartImage,
    by_alias: dict[str, str],
    last_verse: dict[tuple[str, int], int],
    stored: dict[tuple[str, int, int], int],
) -> Placed | str:
    """The chart's passage, from its index reference, and where its note goes: where the
    image stands (S3a's rule — the end of the verse it follows, once its passage has begun)."""
    printed = _ABBREVIATION.sub(r"\1", chart.reference)
    parsed = parse_reference(printed, by_alias, last_verse)
    if isinstance(parsed, str):
        return parsed
    if len(parsed) != 1 or parsed[0][0] != record.book:
        return f"{chart.reference!r} is not one passage in {record.book}, where the chart stands"
    book, part = parsed[0]
    first = (part.start_chapter, part.start_verse)
    last = (part.end_chapter, part.end_verse)
    if record.after is not None and record.after >= first:
        (chapter, verse), at_end = record.after, True
    elif record.before is not None and record.before[0] == book:
        _, chapter, verse = record.before
        at_end = False
    else:
        return f"no verse to stand by in {book} (p{record.page})"
    if (chapter, verse) == last and at_end:
        where = "closes its passage"
    elif first <= (chapter, verse) <= last:
        where = "inside it"
    else:
        where = "after it" if (chapter, verse) > last else "before it"
    kind = shape(printed, part)
    return Placed(
        book=book,
        parts=[part],
        shape=kind,
        whole_chapter=kind == "range"
        and part.start_verse == 1
        and part.end_verse == last_verse.get((book, part.end_chapter)),
        chapter=chapter,
        verse=stored.get((book, chapter, verse), verse),
        at_end=at_end,
        where=where,
        target=target(book, part, chapters=kind == "whole chapters"),
    )


def target(book: str, part: Part, *, chapters: bool) -> str:
    """The ``ref:`` target (ADR-0011) for one part: whole chapters as printed, else verses."""
    if chapters:
        if part.start_chapter == part.end_chapter:
            return f"{book}.{part.start_chapter}"
        return f"{book}.{part.start_chapter}-{part.end_chapter}"
    start = f"{book}.{part.start_chapter}.{part.start_verse}"
    if (part.start_chapter, part.start_verse) == (part.end_chapter, part.end_verse):
        return start
    if part.start_chapter == part.end_chapter:
        return f"{start}-{part.end_verse}"
    return f"{start}-{part.end_chapter}.{part.end_verse}"
