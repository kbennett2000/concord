"""Read ``pdftohtml -xml`` output into typed text items and images.

``pdftohtml -xml`` emits one ``<text>`` element per run of same-styled text, positioned in
page coordinates, plus ``<fontspec>`` elements (size, colour), one ``<image>`` element per
placed image, and the PDF outline. Font size, colour, bold/italic and link targets carry all
of the book's structure, so each item keeps exactly those and nothing else. The images (V8-S4b)
sit in their own list, so the text items are the same as with ``-i``: pdftohtml writes each
image's file next to its output — a JPEG exactly as the PDF stores it — into a directory the
caller owns.
"""

from __future__ import annotations

import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# The colour Calibre gives every hyperlink; links (verse numbers with a study note, ``*``
# markers, callouts, chapter headers) are the only blue text in the book.
LINK_COLOUR = "#0000ee"

_HREF_PAGE = re.compile(r"#(\d+)$")


class PdfXmlError(Exception):
    """The pdftohtml output is missing or not in the expected shape."""


@dataclass(frozen=True, slots=True)
class TextItem:
    """One ``<text>`` run: where it sits, how it looks, what it says, where it links."""

    page: int
    top: int
    left: int
    width: int
    size: int
    blue: bool
    bold: bool
    italic: bool
    text: str
    link_page: int | None

    @property
    def stripped(self) -> str:
        return self.text.strip()


@dataclass(frozen=True, slots=True)
class ImageItem:
    """One ``<image>``: where it sits on its page, its size there, and its extracted file."""

    page: int
    top: int
    left: int
    width: int
    height: int
    src: Path


@dataclass(frozen=True, slots=True)
class OutlineEntry:
    page: int
    title: str


@dataclass(frozen=True, slots=True)
class PdfDocument:
    items: list[TextItem]
    outline: list[OutlineEntry]
    page_count: int
    producer_version: str
    images: list[ImageItem] = field(default_factory=list[ImageItem])


def run_pdftohtml(pdf: Path, out_dir: Path) -> str:
    """Convert ``pdf`` to pdftohtml's XML, its images written into ``out_dir``.

    Never ``-stdout`` here: with it, pdftohtml writes the images next to the PDF."""
    stem = out_dir / "emb"
    try:
        subprocess.run(
            ["pdftohtml", "-xml", "-q", str(pdf), str(stem)],
            capture_output=True,
            check=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PdfXmlError(
            "pdftohtml not found — install poppler-utils (e.g. apt install poppler-utils)"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise PdfXmlError(f"pdftohtml failed on {pdf}: {exc.stderr.strip()}") from exc
    xml = stem.with_suffix(".xml")
    if not xml.is_file():
        raise PdfXmlError(f"pdftohtml wrote no {xml.name} for {pdf}")
    return xml.read_text(encoding="utf-8")


def _int_attr(element: ET.Element, name: str) -> int:
    value = element.get(name)
    if value is None:
        raise PdfXmlError(f"<{element.tag}> lacks {name!r}")
    return int(value)


def _styled(element: ET.Element, tag: str) -> bool:
    """True when a ``tag`` descendant carries non-blank text."""
    return any("".join(child.itertext()).strip() for child in element.iter(tag))


def _link_page(element: ET.Element) -> int | None:
    for anchor in element.iter("a"):
        match = _HREF_PAGE.search(anchor.get("href", ""))
        if match:
            return int(match.group(1))
    return None


def parse_pdf_xml(xml: str) -> PdfDocument:
    """Parse pdftohtml's XML into items (document order) and the outline."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise PdfXmlError(f"pdftohtml output is not well-formed XML: {exc}") from exc
    if root.tag != "pdf2xml":
        raise PdfXmlError(f"expected a <pdf2xml> root, got <{root.tag}>")

    fonts: dict[str, tuple[int, bool]] = {}
    items: list[TextItem] = []
    images: list[ImageItem] = []
    pages = 0
    for page in root.iter("page"):
        pages += 1
        number = _int_attr(page, "number")
        for element in page:
            if element.tag == "fontspec":
                fid = element.get("id", "")
                fonts[fid] = (
                    _int_attr(element, "size"),
                    element.get("color", "").lower() == LINK_COLOUR,
                )
            elif element.tag == "text":
                font = fonts.get(element.get("font", ""))
                if font is None:
                    raise PdfXmlError(f"page {number}: <text> uses an undeclared font")
                items.append(
                    TextItem(
                        page=number,
                        top=_int_attr(element, "top"),
                        left=_int_attr(element, "left"),
                        width=_int_attr(element, "width"),
                        size=font[0],
                        blue=font[1],
                        bold=_styled(element, "b"),
                        italic=_styled(element, "i"),
                        text="".join(element.itertext()),
                        link_page=_link_page(element),
                    )
                )
            elif element.tag == "image":
                images.append(
                    ImageItem(
                        page=number,
                        top=_int_attr(element, "top"),
                        left=_int_attr(element, "left"),
                        width=_int_attr(element, "width"),
                        height=_int_attr(element, "height"),
                        src=Path(element.get("src", "")),
                    )
                )

    outline = [
        OutlineEntry(page=int(entry.get("page", "0")), title="".join(entry.itertext()).strip())
        for entry in root.iter("item")
        if entry.get("page")
    ]
    return PdfDocument(
        items=items,
        outline=outline,
        page_count=pages,
        producer_version=root.get("version", ""),
        images=images,
    )
