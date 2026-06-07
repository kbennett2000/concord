"""Smoke test for examples/embed_in_process.py — the in-process embedding reference.

Lives here (not bible-api/tests) because the example imports `bible_core` and, optionally,
`bible_semantic` — never the web layer — and this package sits above core and below the API.

The fast test exercises the core path (parse + fetch over a synthetic bible.db, no HTTP) and
asserts the semantic half skips gracefully when the vector store is absent — forced
deterministically by pointing CONCORD_EMBEDDINGS_PATH at a missing file, so it holds whether or
not a real store/model happens to be present locally. The real semantic path is an
`@pytest.mark.integration` test that skips cleanly without the baked store + fetched model.
"""
# the integration guard reads the model module's precision→filename map (a private symbol)
# pyright: reportPrivateUsage=false

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest
from bible_core.loader import build_database

_EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "embed_in_process.py"


def _load_example() -> ModuleType:
    spec = importlib.util.spec_from_file_location("embed_in_process_example", _EXAMPLE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_synthetic_db(tmp_path: Path) -> Path:
    """A one-translation, two-verse bible.db built through the real loader (public API)."""
    data_dir = tmp_path / "translations"
    data_dir.mkdir()
    payload = {
        "code": "TST",
        "name": "Test Version",
        "language": "en",
        "copyright": "Public domain.",
        "books": [
            {
                "abbreviation": "John",
                "name": "John",
                "order_index": 43,
                "chapters": [
                    {
                        "number": 3,
                        "verses": [
                            {"number": 16, "text": "For God so loved the world."},
                            {"number": 17, "text": "For God sent not his Son to condemn."},
                        ],
                    }
                ],
            }
        ],
    }
    (data_dir / "tst.json").write_text(json.dumps(payload))
    db_path = tmp_path / "bible.db"
    build_database(db_path, [data_dir])
    return db_path


def test_core_fetch_in_process(tmp_path: Path) -> None:
    example = _load_example()
    db_path = _build_synthetic_db(tmp_path)
    reference, text = example.fetch_verse_in_process(db_path, "John 3:16", "TST")
    assert reference.book_id == "JHN"
    assert reference.echo == "John 3:16"
    assert text == "For God so loved the world."


def test_semantic_skips_gracefully_when_store_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    example = _load_example()
    db_path = _build_synthetic_db(tmp_path)
    # Force the vector store to be unavailable → the example returns None rather than raising.
    monkeypatch.setenv("CONCORD_EMBEDDINGS_PATH", str(tmp_path / "no-such-embeddings.db"))
    assert example.semantic_search_in_process(db_path, "love") is None


def test_main_runs_and_reports_skip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    example = _load_example()
    db_path = _build_synthetic_db(tmp_path)
    monkeypatch.setenv("CONCORD_EMBEDDINGS_PATH", str(tmp_path / "no-such-embeddings.db"))
    code = example.main(["--db", str(db_path), "--ref", "John 3:16", "--translation", "TST"])
    assert code == 0


def test_main_missing_db_returns_1(tmp_path: Path) -> None:
    example = _load_example()
    assert example.main(["--db", str(tmp_path / "absent.db")]) == 1


@pytest.mark.integration
def test_semantic_search_in_process_real() -> None:
    """The real embedding path, against the baked store + fetched model. Skips without them."""
    from bible_semantic.build import default_embeddings_path
    from bible_semantic.model import _ONNX_FILENAMES, model_dir, model_precision

    bible_db = Path("bible.db")
    if not bible_db.is_file():
        pytest.skip("bible.db not found — build it via bible_core.loader")
    if not default_embeddings_path().is_file():
        pytest.skip("embeddings.db not built — run scripts/build_embeddings.py")
    precision = model_precision()
    if not (model_dir() / "onnx" / _ONNX_FILENAMES[precision]).is_file():
        pytest.skip(f"{precision} model not present — run scripts/fetch_model.py")

    example = _load_example()
    results = example.semantic_search_in_process(bible_db, "do not be anxious", k=10)
    assert results is not None and len(results) > 0
    scores = [score for _, score, _ in results]
    assert scores == sorted(scores, reverse=True)
    # Hits are hydrated from the embedded translation, so text comes back.
    assert all(text for _, _, text in results)
