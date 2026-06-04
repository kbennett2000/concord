#!/usr/bin/env python3
"""Fetch the embedding model + tokenizer into the gitignored models/ directory.

Build/test-time only — the runtime never downloads anything. Uses only the standard
library (no new dependency) and pins an exact revision SHA so every fetch is byte-identical
and reproducible (no silent drift from the upstream `main` branch).

Run from the repo root:

    uv run python scripts/fetch_model.py

Files already present are left untouched (idempotent). Any HTTP error fails loudly.
"""

from __future__ import annotations

import sys
import urllib.error
import urllib.request

from bible_semantic.model import MODEL_ID, MODEL_REVISION, model_dir

# Files needed for S0 inference: the fp32 ONNX graph, the self-contained tokenizer, and
# config.json (metadata / future embedding_meta guard). int8 weights are an S3 concern.
_FILES = ["onnx/model.onnx", "tokenizer.json", "config.json"]

_BASE_URL = f"https://huggingface.co/{MODEL_ID}/resolve/{MODEL_REVISION}"


def _download(url: str, dest_path: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "concord-fetch-model"})
    with urllib.request.urlopen(request) as response:  # noqa: S310 (trusted HTTPS host)
        total = response.headers.get("Content-Length")
        size_note = f" ({int(total) / 1e6:.1f} MB)" if total else ""
        print(f"  downloading{size_note} ...", flush=True)
        with open(dest_path, "wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)


def main() -> int:
    target = model_dir()
    print(f"Model:    {MODEL_ID}")
    print(f"Revision: {MODEL_REVISION}")
    print(f"Target:   {target}")

    for rel in _FILES:
        dest = target / rel
        if dest.is_file():
            print(f"- {rel}: already present, skipping")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        url = f"{_BASE_URL}/{rel}"
        print(f"- {rel}: {url}")
        try:
            _download(url, str(dest))
        except urllib.error.HTTPError as exc:
            print(f"ERROR fetching {url}: HTTP {exc.code} {exc.reason}", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            print(f"ERROR fetching {url}: {exc.reason}", file=sys.stderr)
            return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
