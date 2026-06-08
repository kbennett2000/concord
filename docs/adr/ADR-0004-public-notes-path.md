# ADR-0004: A committed, ship-by-default public notes path (`data/notes/`)

**Status:** Accepted

<!--
Records the v4-followup change that lets public-domain translator's notes ship in the stock image
(roadmap item #1). The v4 SPEC (docs/v4/SPEC.md §2) made notes private-only by design; this ADR
introduces a second, public notes path without weakening that. Format mirrors ADR-0001/0002/0003:
Context / Options / Decision / Consequences.
-->

## Context

v4 shipped translator's notes as a **private-only** feature. The build-time loader
([bible_core.notes](../../bible-core/src/bible_core/notes.py)) scanned a single notes directory,
hardcoded by [bible_core.loader](../../bible-core/src/bible_core/loader.py) to
`data/private/notes/`. That directory sits under `data/private/`, which the **dual-ignore rule**
(docs/v4/SPEC.md §2) keeps out of *both* `.gitignore` and `.dockerignore` — the only barrier
stopping the Dockerfile's broad `COPY data/ data/` from baking restricted data into the image. The
documented consequence: the published image ships **zero** notes, and
`GET /v1/translations/{t}/notes/{book}/{chapter}` returns an empty list for every translation on a
stock build.

That is correct for *restricted* notes (e.g. the NET Bible's, "all rights reserved"). But the World
English Bible's own translator footnotes are **public domain** — `data/translations/WEB.json`
already declares `"The World English Bible is in the public domain."` — and *should* ship. With only
one private, dual-ignored notes path, there was nowhere to put notes that are meant to be committed
and baked into the public image.

The design question: how do we ship public-domain notes by default **without weakening** the
never-ship guarantee for `data/private/`?

## Options considered

- **(A) Relax the dual-ignore on `data/private/notes/`** (un-ignore just the notes subdir). Rejected
  outright: it directly erodes the load-bearing safety invariant and invites a future restricted
  notes file into the image. The whole value of dual-ignore is that it is absolute.
- **(B) Bake public notes from inside `data/translations/WEB.json`** (re-populate its empty
  chapter-level `footnotes` arrays and have the translation loader emit notes). Rejected: it
  overloads the translation file/loader with a second concern, and would mean re-deriving WEB's text
  to source the footnotes — risking text drift. Notes ingestion already has its own validated,
  idempotent pipeline; reuse it.
- **(C) A second, committed, ship-by-default notes path `data/notes/`, scanned by the loader
  *alongside* `data/private/notes/`.** The public path is committed and stays out of the ignore
  files (so it ships); the private path keeps its dual-ignore untouched. The loader takes a *list* of
  notes dirs and unions them. **Chosen.**

Within (C), the loader-shape choice: a dedicated second parameter vs. generalizing the single
`notes_dir` to a `notes_dirs: list[Path]`. The list mirrors the existing `cross_ref_dirs:
list[Path]` pattern already in `build_database`, keeps one ingest code path, and makes "scan these
directories, union the results" the natural contract. **List chosen.**

## Decision

Introduce **`data/notes/`** — a committed, public-domain notes directory that is in the Docker build
context and is deliberately **NOT** added to `.gitignore` or `.dockerignore`. The loader scans a
**list** of notes directories, in order:

```
notes_dirs = [data/notes, data/private/notes]
```

- `build_database(...)`'s `notes_dir: Path | None` becomes `notes_dirs: list[Path] | None`;
  `bible_core.notes.load_notes` takes the list and iterates `discover_notes_files_in_dirs`, which
  scans each directory non-recursively (`*.json`) in the given order, sorted by path within each.
- **Union, deterministic order.** Note ids are assigned by walking the discovered files in dir order
  (public first), then sorted filename — so the build stays byte-identical and reproducible. If the
  **same translation** carries notes in both paths (e.g. a private `WEB.json` beside the committed
  public one), **both load** — a union, public ids before private. This is documented behavior, not
  an error (no dedup; the two files are assumed to carry different notes).
- `data/private/` keeps its dual-ignore **untouched**. A clean build (no `data/private/`) bakes the
  committed public notes and **zero** private notes.

## Consequences

- **The dual-ignore invariant is preserved and now has a mirror guard.** `data/private/` stays in
  both ignore files (`test_private_data_dir_is_ignored`); a new
  `test_public_notes_dir_is_not_ignored` fails loudly if `data/notes/` ever lands in an ignore file
  — which would silently drop the public notes from the repo and image. The behavioral proof evolved
  from "clean build → zero notes" to **"clean build → bakes public notes, zero private notes"**
  (`test_clean_build_bakes_public_notes_but_zero_private_notes`).
- **The stock image now serves WEB's PD footnotes**, while every other translation remains
  empty-on-stock — an honest "no notes loaded" 200, unchanged. No API contract change: the notes
  endpoints, schema, and response shapes are identical; only the baked data grows. Purely additive.
- **One ingest path, reused.** Public and private notes share the same validated, idempotent loader,
  JSON contract (docs/v4/notes-ingest.md), and FTS index — no parallel code.
- **`bible-core` stays web-free and the runtime stays offline.** Public notes are committed JSON
  baked at build; sourcing them (the WEB USFM parse) is a build/dev-time step, never a runtime
  dependency.
- **Same-translation-in-both-paths is a union, not a merge.** Chosen for simplicity and
  determinism; if de-duplication across paths is ever needed it is a future, separable concern.
