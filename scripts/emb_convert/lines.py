"""Group text items into visual lines.

pdftohtml writes items in reading order. Items of one line share a page and sit within a few
points of each other's ``top``: a verse number rides 1–2 points high and a small-caps "ORD"
3 points low, while the next line is 14+ points down. An item joins the current line when it
sits within reach of any item already on it. A cell set between two lines (a table
number centred on a wrapped name) becomes its own line, which the table rules expect.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from emb_convert.pdfxml import TextItem

SAME_LINE = 4


@dataclass(slots=True)
class Line:
    page: int
    top: int
    items: list[TextItem] = field(default_factory=list[TextItem])

    @property
    def nonblank(self) -> list[TextItem]:
        return [item for item in self.items if item.stripped]

    @property
    def right(self) -> int:
        return max((i.left + i.width for i in self.nonblank), default=0)

    @property
    def text(self) -> str:
        return "".join(item.text for item in self.items)


def group_lines(items: list[TextItem]) -> list[Line]:
    lines: list[Line] = []
    for item in items:
        last = lines[-1] if lines else None
        if (
            last is not None
            and last.page == item.page
            and any(abs(item.top - other.top) <= SAME_LINE for other in last.items)
        ):
            last.items.append(item)
        else:
            lines.append(Line(page=item.page, top=item.top, items=[item]))
    return lines
