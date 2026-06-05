"""The connection helper enables foreign keys and name-based row access."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from bible_core.db import connect, connect_readonly


def test_connect_enables_foreign_keys() -> None:
    conn = connect(":memory:")
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_readonly_connection_usable_across_threads(tmp_path: Path) -> None:
    """A read-only connection must be usable from a thread other than the one that opened it.

    Reproduces the FastAPI case: sync endpoints run in a threadpool, and a generator
    dependency's ``finally: conn.close()`` can run on a *different* worker thread than the
    one that opened the connection. With the default ``check_same_thread=True`` that raises
    ``sqlite3.ProgrammingError`` and surfaces as an intermittent HTTP 500 (found on the
    Optiplex during S3b). Each request has its own connection, so the usage is never
    concurrent — only cross-thread.
    """
    db = tmp_path / "x.db"
    sqlite3.connect(db).close()  # create a valid (empty) file so mode=ro can open it

    conn = connect_readonly(db)  # opened in this thread
    errors: list[Exception] = []

    def use_then_close() -> None:
        try:
            conn.execute("SELECT 1").fetchone()
            conn.close()
        except Exception as exc:  # noqa: BLE001 - the assertion reports whatever was raised
            errors.append(exc)

    worker = threading.Thread(target=use_then_close)
    worker.start()
    worker.join()
    assert not errors, errors


def test_connect_uses_row_factory() -> None:
    conn = connect(":memory:")
    conn.execute("CREATE TABLE t (a, b)")
    conn.execute("INSERT INTO t VALUES (1, 2)")
    row = conn.execute("SELECT a, b FROM t").fetchone()
    assert row["a"] == 1
    assert row["b"] == 2
