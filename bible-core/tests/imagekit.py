"""Tiny real images made in the test — never a file from any book (SPEC v8 §2).

``png`` is a complete PNG (one grey pixel row repeated); ``jpeg`` a complete baseline greyscale
JPEG, every 8×8 block mid-grey, with one-symbol Huffman tables (DC difference 0, then EOB).
Both decode in any viewer; the loader only reads their headers.
"""

from __future__ import annotations

import struct
import zlib


def png(width: int = 3, height: int = 2) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)  # 8-bit greyscale
    rows = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def jpeg(width: int = 3, height: int = 2) -> bytes:
    def segment(marker: int, body: bytes) -> bytes:
        return struct.pack(">BBH", 0xFF, marker, len(body) + 2) + body

    one_code = bytes([1] + [0] * 15)  # a single symbol with a one-bit code
    blocks = -(-width // 8) * -(-height // 8)
    bits = "00" * blocks  # per block: DC category 0, then end-of-block
    bits += "1" * (-len(bits) % 8)
    scan = bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits), 8))
    return (
        b"\xff\xd8"
        + segment(0xDB, b"\x00" + b"\x01" * 64)  # quantisation table 0, all ones
        + segment(0xC0, struct.pack(">BHHBBBB", 8, height, width, 1, 1, 0x11, 0))
        + segment(0xC4, b"\x00" + one_code + b"\x00")  # DC table 0: symbol 0
        + segment(0xC4, b"\x10" + one_code + b"\x00")  # AC table 0: end-of-block
        + segment(0xDA, bytes([1, 1, 0x00, 0, 63, 0]))
        + scan
        + b"\xff\xd9"
    )
