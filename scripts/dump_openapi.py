#!/usr/bin/env python3
"""Export the FastAPI OpenAPI schema to ``docs/openapi.json`` — the published ``/v1`` contract.

This is the *producer* half of the contract Concord shares with downstream consumers (e.g.
songbird): the schema is committed so a response-shape change can't merge without updating the
artifact, and a CI drift check (`make openapi-check`) enforces that.

``create_app(enable_semantic=False)`` is DB- and model-free (the lifespan that opens ``bible.db``
runs only on startup, not on construction) and registers every route unconditionally, so the
schema is the full, stable surface. The output is rendered deterministically (sorted keys,
two-space indent, trailing newline) so the committed file diffs cleanly. ``info.version`` flows
from ``bible_api.__version__`` — the artifact is versioned with the release for free.

Usage::

    python scripts/dump_openapi.py            # regenerate docs/openapi.json
    python scripts/dump_openapi.py --check     # verify it's up to date (exit 1 on drift)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from bible_api.app import create_app

OPENAPI_PATH = Path(__file__).resolve().parents[1] / "docs" / "openapi.json"


def render() -> str:
    """Return the OpenAPI schema as deterministic JSON text (sorted keys, trailing newline)."""
    app = create_app(enable_semantic=False)
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify docs/openapi.json matches the freshly-generated schema; exit 1 on drift",
    )
    args = parser.parse_args(argv)

    rendered = render()
    if args.check:
        current = OPENAPI_PATH.read_text(encoding="utf-8") if OPENAPI_PATH.exists() else ""
        if current != rendered:
            print(
                f"{OPENAPI_PATH} is out of date — run `make openapi` and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{OPENAPI_PATH} is up to date.")
        return 0

    OPENAPI_PATH.write_text(rendered, encoding="utf-8")
    print(f"wrote {OPENAPI_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
