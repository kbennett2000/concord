"""Build-time images loader — a translation's assets (v8, ADR-0012).

Reads image files from one or more assets directories and populates ``translation_assets``:
the bytes exactly as supplied, their media type and pixel size, under a name unique within the
translation. A note's ``image`` names one (ADR-0011, made live by ADR-0012).

**Where.** ``<assets dir>/<CODE>/<name>`` — one folder per translation, named by its exact id.
The CLI scans ``data/private/assets/`` only: images there are user-supplied (the charts of a
study Bible the operator owns), dual-ignored like everything under ``data/private/``, so a clean
build bakes **zero** assets. A missing directory loads nothing — not an error.

**Rules (each violation fails the build, naming the file).**

- The folder names a loaded translation; nothing but folders sits directly in an assets
  directory, and nothing but files inside a translation's folder.
- A name is lower-case ASCII letters, digits, ``-`` and ``_`` (starting with a letter or digit,
  at most 64 characters) and then ``.jpg``, ``.jpeg`` or ``.png``.
- The bytes are a complete JPEG (``image/jpeg``) or PNG (``image/png``), sniffed from the
  content, and the extension agrees. No other type is accepted.
- Width and height are read from the header (JPEG: the first SOF segment; PNG: ``IHDR``), each
  from 1 to ``MAX_DIMENSION``; the file is non-empty and at most ``MAX_ASSET_BYTES``.

Pure stdlib (``struct`` + ``sqlite3``) — ``bible-core`` stays web-free and ML-free. The EMB
converter reads its charts' sizes with the same ``image_header``.
"""

from __future__ import annotations

import re
import sqlite3
import struct
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from .loader import LoaderError

MAX_ASSET_BYTES = 2 * 1024 * 1024
MAX_DIMENSION = 8192

ASSET_NAME = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\.(jpg|jpeg|png)")

MEDIA_TYPES: frozenset[str] = frozenset({"image/jpeg", "image/png"})

_EXTENSION_TYPE = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# Start-of-frame markers carry the frame's size; C4 (DHT), C8 (JPG) and CC (DAC) share the
# range but are not frames.
_JPEG_SOF = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}
# Markers that stand alone, with no length field: TEM and RST0-7 (SOI/EOI end the walk).
_JPEG_STANDALONE = frozenset({0x01, *range(0xD0, 0xD8)})

# (translation_id, name, media_type, width, height, bytes)
AssetRow = tuple[str, str, str, int, int, bytes]


class ImageError(ValueError):
    """The bytes are not a complete JPEG or PNG this loader accepts."""


@dataclass(frozen=True)
class AssetsStats:
    assets: int
    asset_bytes: int


def _jpeg_size(data: bytes) -> tuple[int, int]:
    if not data.endswith(b"\xff\xd9"):
        raise ImageError("not a complete JPEG (no end-of-image marker)")
    at = 2
    while at + 4 <= len(data):
        if data[at] != 0xFF:
            raise ImageError(f"not a valid JPEG (no marker at byte {at})")
        marker = data[at + 1]
        if marker == 0xFF:  # fill byte before a marker
            at += 1
            continue
        if marker in _JPEG_STANDALONE:
            at += 2
            continue
        if marker in (0xD9, 0xDA):  # end of image, or scan data before any frame header
            break
        (length,) = struct.unpack(">H", data[at + 2 : at + 4])
        if marker in _JPEG_SOF:
            if length < 7 or at + 9 > len(data):
                raise ImageError("not a valid JPEG (short frame header)")
            height, width = struct.unpack(">HH", data[at + 5 : at + 9])
            return width, height
        at += 2 + length
    raise ImageError("not a valid JPEG (no frame header before the image data)")


def _png_size(data: bytes) -> tuple[int, int]:
    if len(data) < 33 or data[12:16] != b"IHDR":
        raise ImageError("not a valid PNG (no IHDR chunk first)")
    if not data.endswith(b"IEND\xaeB`\x82"):
        raise ImageError("not a complete PNG (no IEND chunk last)")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def image_header(data: bytes) -> tuple[str, int, int]:
    """Sniff ``data``: ``(media_type, width, height)`` for a complete JPEG or PNG.

    Raises ``ImageError`` for anything else, a truncated file, or a size outside
    1..``MAX_DIMENSION``. Reads headers only — the image is never decoded."""
    if data.startswith(b"\xff\xd8\xff"):
        media_type = "image/jpeg"
        width, height = _jpeg_size(data)
    elif data.startswith(_PNG_SIGNATURE):
        media_type = "image/png"
        width, height = _png_size(data)
    else:
        raise ImageError("not a JPEG or PNG")
    if not (1 <= width <= MAX_DIMENSION and 1 <= height <= MAX_DIMENSION):
        raise ImageError(f"its size {width}x{height} is outside 1 to {MAX_DIMENSION} pixels a side")
    return media_type, width, height


def _read_asset(path: Path, translation_id: str, where: str) -> AssetRow:
    match = ASSET_NAME.fullmatch(path.name)
    if match is None:
        raise LoaderError(
            f"{where}: not a valid asset name (lower-case letters, digits, '-' and '_', "
            "then .jpg, .jpeg or .png)."
        )
    data = path.read_bytes()
    if not data:
        raise LoaderError(f"{where}: the file is empty.")
    if len(data) > MAX_ASSET_BYTES:
        raise LoaderError(
            f"{where}: {len(data):,} bytes is over the {MAX_ASSET_BYTES:,}-byte limit."
        )
    try:
        media_type, width, height = image_header(data)
    except ImageError as exc:
        raise LoaderError(f"{where}: {exc}.") from exc
    expected = _EXTENSION_TYPE[match.group(1)]
    if media_type != expected:
        kind = "JPEG" if media_type == "image/jpeg" else "PNG"
        raise LoaderError(f"{where}: the file is a {kind}, but its name ends in .{match.group(1)}.")
    return (translation_id, path.name, media_type, width, height, data)


def read_assets(assets_dir: Path, translation_ids: frozenset[str]) -> list[AssetRow]:
    """Every asset under ``assets_dir``, validated, in sorted-path order."""
    if not assets_dir.is_dir():
        return []
    rows: list[AssetRow] = []
    for folder in sorted(assets_dir.iterdir(), key=lambda p: p.name):
        where = f"assets/{folder.name}"
        if not folder.is_dir():
            raise LoaderError(
                f"{where}: only translation folders belong in an assets directory "
                "(put images in assets/<CODE>/)."
            )
        if folder.name not in translation_ids:
            known = ", ".join(sorted(translation_ids))
            raise LoaderError(
                f"{where}: translation {folder.name!r} is not a loaded translation. "
                f"Known translations: {known}."
            )
        for path in sorted(folder.iterdir(), key=lambda p: p.name):
            if not path.is_file():
                raise LoaderError(f"{where}/{path.name}: not a file (no sub-folders).")
            rows.append(_read_asset(path, folder.name, f"{where}/{path.name}"))
    return rows


def load_assets(
    conn: sqlite3.Connection, assets_dirs: Sequence[Path], translation_ids: frozenset[str]
) -> tuple[AssetsStats, Mapping[str, frozenset[str]]]:
    """Ingest every assets directory into ``translation_assets``.

    Returns the stats and, per translation, the names loaded — the notes loader checks each
    note's ``image`` against them. A name given twice for one translation fails."""
    rows: list[AssetRow] = []
    names: dict[str, set[str]] = {}
    for assets_dir in assets_dirs:
        for row in read_assets(assets_dir, translation_ids):
            taken = names.setdefault(row[0], set())
            if row[1] in taken:
                raise LoaderError(
                    f"assets/{row[0]}/{row[1]}: translation {row[0]!r} already has an asset "
                    "by that name."
                )
            taken.add(row[1])
            rows.append(row)
    conn.executemany(
        "INSERT INTO translation_assets "
        "(translation_id, name, media_type, width, height, bytes) VALUES (?, ?, ?, ?, ?, ?)",
        rows,
    )
    stats = AssetsStats(assets=len(rows), asset_bytes=sum(len(row[5]) for row in rows))
    return stats, {tid: frozenset(taken) for tid, taken in names.items()}
