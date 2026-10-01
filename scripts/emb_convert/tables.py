"""Tables inside the Bible text (Numbers' census lists, Ezra/Nehemiah's returnees, Rev 7).

A table row starts at the table margin (x≈40, between prose's 38 and poetry's 46+) and its
cells are separated by wide gaps; prose items sit edge to edge. A run of such lines is a
table when it has at least two rows, or a bold-italic header row plus one. A lone wide-gap
line is justification, not a table, and is only counted.

Rows become text the way the operator's NLT file sets Numbers 1–2: cells joined with " - ",
rows inside one verse separated by a space, header rows dropped. A row whose right-hand cell
landed alone at the bottom of the previous page (Num 1:6–7) gets that cell back.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from emb_convert.lines import Line
from emb_convert.pdfxml import TextItem

TABLE_LEFT = range(39, 42)
CELL_GAP = 12
COLUMN_TOLERANCE = 10
CELL_SEPARATOR = " - "

VerseNumberTest = Callable[[TextItem], bool]


def cells(items: list[TextItem]) -> list[list[TextItem]]:
    """Split a line's non-blank items (left to right) into cells at wide gaps."""
    ordered = sorted(items, key=lambda i: i.left)
    groups: list[list[TextItem]] = []
    for item in ordered:
        if groups:
            last = groups[-1][-1]
            if item.left - (last.left + last.width) <= CELL_GAP:
                groups[-1].append(item)
                continue
        groups.append([item])
    return groups


def _starts_at_margin(line: Line) -> bool:
    content = line.nonblank
    return bool(content) and min(i.left for i in content) in TABLE_LEFT


def is_header_row(line: Line) -> bool:
    content = line.nonblank
    return (
        _starts_at_margin(line)
        and len(cells(content)) >= 2
        and all(i.bold and i.italic for i in content)
    )


def is_row(line: Line) -> bool:
    content = line.nonblank
    return _starts_at_margin(line) and len(cells(content)) >= 2 and not is_header_row(line)


@dataclass(slots=True)
class Table:
    """A run of table lines, by index into the line list."""

    first: int
    last: int  # inclusive
    columns: list[int]  # left x of each column after the first
    header_rows: int = 0
    rows: int = 0
    split_cells_moved: int = 0
    where: str = ""  # filled by the parser: "NUM 1:5-15"


@dataclass(slots=True)
class TableScan:
    tables: list[Table] = field(default_factory=list[Table])
    lone_wide_lines: list[int] = field(default_factory=list[int])


def _column_of(x: int, columns: list[int]) -> int | None:
    for index, column in enumerate(columns):
        if abs(x - column) <= COLUMN_TOLERANCE:
            return index + 1
    return None


def find_tables(lines: list[Line]) -> TableScan:
    """Locate every table run in ``lines``."""
    scan = TableScan()
    i = 0
    while i < len(lines):
        if not (is_row(lines[i]) or is_header_row(lines[i])):
            i += 1
            continue
        start = i
        columns: list[int] = []
        row_lines = 0
        j = i
        while j < len(lines):
            line = lines[j]
            content = line.nonblank
            if not content:
                j += 1
                continue
            if is_header_row(line) or is_row(line):
                for cell in cells(content)[1:]:
                    if _column_of(cell[0].left, columns) is None:
                        columns.append(cell[0].left)
                row_lines += 0 if is_header_row(line) else 1
                j += 1
                continue
            groups = cells(content)
            if len(groups) == 1 and (
                _starts_at_margin(line) or _column_of(groups[0][0].left, columns) is not None
            ):
                j += 1
                continue
            break
        has_header = is_header_row(lines[start])
        if row_lines >= 2 or (has_header and row_lines >= 1):
            scan.tables.append(Table(first=start, last=j - 1, columns=sorted(columns)))
            i = j
        else:
            scan.lone_wide_lines.append(start)
            i = start + 1
    return scan


@dataclass(slots=True)
class Row:
    """One table row: its leading verse-number items and its cells' lines of items."""

    lead: list[TextItem]
    cells: dict[int, list[list[TextItem]]]


def _split_lead(
    first_cell: list[TextItem], is_verse_number: VerseNumberTest
) -> tuple[list[TextItem], list[TextItem]]:
    lead: list[TextItem] = []
    rest = list(first_cell)
    while rest and is_verse_number(rest[0]):
        lead.append(rest.pop(0))
    return lead, rest


def build_rows(
    table: Table,
    lines: list[Line],
    is_verse_number: VerseNumberTest,
    *,
    fix_split_rows: bool,
) -> list[Row]:
    """Assemble a table's lines into rows (header rows dropped)."""
    rows: list[Row] = []
    orphans: dict[int, list[list[TextItem]]] = {}
    for line in lines[table.first : table.last + 1]:
        content = line.nonblank
        if not content:
            continue
        if is_header_row(line):
            table.header_rows += 1
            continue
        groups = cells(content)
        first_left = groups[0][0].left
        if first_left in TABLE_LEFT:
            lead, first = _split_lead(groups[0], is_verse_number)
            if lead or len(groups) >= 2 or not rows:
                row = Row(lead=lead, cells={0: [first]} if first else {})
                for column, lines_of in orphans.items():
                    row.cells.setdefault(column, []).extend(lines_of)
                    table.split_cells_moved += 1
                orphans.clear()
                rows.append(row)
            else:
                rows[-1].cells.setdefault(0, []).append(first)
            for cell in groups[1:]:
                column = _column_of(cell[0].left, table.columns) or len(table.columns)
                rows[-1].cells.setdefault(column, []).append(cell)
            continue
        column = _column_of(first_left, table.columns) or len(table.columns)
        current = rows[-1] if rows else None
        if current is not None and column not in current.cells:
            current.cells[column] = [groups[0]]
        elif fix_split_rows or current is None:
            orphans.setdefault(column, []).append(groups[0])
        else:
            current.cells.setdefault(column, []).append(groups[0])
    if orphans and rows:  # an orphan with no following row stays with the last one
        for column, lines_of in orphans.items():
            rows[-1].cells.setdefault(column, []).extend(lines_of)
    table.rows = len(rows)
    return rows
