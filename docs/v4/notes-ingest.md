# Translator's notes — ingest & user flow (Concord v4)

Concord can **store and serve translator's notes** (NET-style study / translator's /
text-critical notes anchored to points in the verse text). The richest source — the NET Bible —
is **copyrighted by Biblical Studies Press, "all rights reserved," and is not redistributable.**
So Concord ships the *capability*, never the *data*: you supply your own legally-obtained notes,
and they are baked into your **local** `bible.db`. The published image ships **zero** notes.

> **Only load data you have the legal right to use.** Notes you place under `data/private/`
> are never committed and never baked into the published image — that is your responsibility to
> keep clean, and Concord's pipeline is built to make it automatic.

## The user flow

1. **Obtain** the source you legally own (e.g. your purchased NET Bible PDF).
2. **Parse** it into Concord's notes JSON with the MIT-licensed NET parser (ported from
   `kbennett2000/net-bible-study`, as used by soap-journal). The parser is *code only* — its
   output for the NET Bible is restricted and stays local.
   *(Status: as of v4 Slice 1 the parser has not yet been vendored into Concord. The ingest
   capability is in place against the JSON contract below; the parser port is a planned
   follow-up. Until then, produce JSON matching the contract by whatever means you legally can.)*
3. **Drop** the JSON at `data/private/notes/<TRANSLATION>.json` — one file per translation, where
   `<TRANSLATION>` is a loaded translation's code (e.g. `NET`). This directory is a *subdirectory*
   of the already-gitignored, dockerignored `data/private/`, so nothing you put there can leak.
4. **Rebuild** Concord (`python -m bible_core.loader`, or rebuild the Docker image locally). The
   loader discovers the notes, validates them, and bakes them into your local `bible.db`.

The build summary then reports the notes it loaded, e.g.:

```
Built bible.db: 17 translations, …, 58000 notes, 16000 note cross-references in 7.1s.
```

A build with no `data/private/notes/` (the public image, CI, or any fresh clone) bakes **zero**
notes — the endpoint (Slice 2) will simply return an empty list for translations with no notes.

## The notes JSON contract

One file per translation. The loader (`bible_core.notes`) reads every `*.json` directly under
`data/private/notes/`.

```jsonc
{
  "translation": "NET",          // REQUIRED — must match a loaded translation's code
  "notes": [
    {
      "book": "JHN",             // REQUIRED — book code or any seeded alias ("John", "Jn", …)
      "chapter": 3,              // REQUIRED — int >= 1
      "verse": 16,               // REQUIRED — int >= 1  (the canonical anchor)
      "text": "The Greek …",     // REQUIRED — non-empty note body
      "type": "tn",              // optional — one of: tn | sn | tc | map | other  (NULL if omitted)
      "char_offset": 12,         // optional — point anchor into the verse text; int >= 0 (default 0)
      "marker": "1",             // optional — the source's superscript marker
      "ordinal": 1,              // optional — render order within the verse
                                 //            (default: 1-based position among that verse's notes)
      "cross_references": [      // optional — references THIS note carries
        { "book": "ROM", "chapter": 8, "verse_start": 1, "verse_end": null }
        // verse_end null = single verse; otherwise a range (>= verse_start)
      ],
      // --- optional v8 fields (ADR-0011); NET uses none of them ---
      "label": "Study Note",     // optional — the source's own name for the kind, for display
      "title": "Love for the world", // optional — the item's heading
      "text_format": "markdown", // optional — "markdown" when text is Markdown; omit = plain text
      "passages": [              // optional — ranges covered beyond the anchor, in the same book
        { "start_chapter": 3, "start_verse": 16, "end_chapter": 3, "end_verse": 21 }
        // a range may cross chapters; a note may have several
      ],
      "image": "chart-01.jpg"    // optional (ADR-0012) — one of this translation's images
    }
  ]
}
```

Notes on the contract:

- **Anchoring** is by **canonical coordinates** (`book` + `chapter` + `verse`) plus the file's
  `translation` — matching how `cross_references` and `place_verses` already anchor. Notes are
  translation-specific because `char_offset` indexes into *that translation's* verse text.
- The anchor is a **point** (`char_offset`), not a span — a marker renders at a position
  (SPEC v4 §4).
- `note_type` is a **constrained set** (`tn`/`sn`/`tc`/`map`/`other`, plus `article` and `chart`
  for v8 study Bibles); omit it for a plain footnote (stored as `NULL`).
- **The v8 fields are optional** ([ADR-0011](../adr/ADR-0011-v8-note-fields.md)). The API returns
  them as `null` (or `[]` for `passages`) when a source doesn't use them.
  - `label` and `title` must be non-empty strings.
  - `text_format` accepts only `"markdown"`.
  - A passage's four numbers are ≥ 1, and its end is not before its start.
  - `image` names one of the same translation's images (below).
- **References inside Markdown text** are `ref:` links: `[see John 3:16](ref:JHN.3.16)`. The target
  is a USFM book code plus `.C`, `.C-C`, `.C.V`, `.C.V-V` or `.C.V-C.V`; ADR-0011 has the exact
  grammar.
- The loader **fails loudly** (`LoaderError`) on malformed input, naming the file and note:
  - unknown translation or unknown book;
  - bad note type, empty text or negative `char_offset`;
  - invalid JSON;
  - an empty `label` or `title`, or a `text_format` other than `"markdown"`;
  - a malformed or backwards passage;
  - an `image` that names no image of the file's translation;
  - a `ref:` target outside the grammar.
- The load is **idempotent** — note ids are assigned deterministically (files in sorted-path
  order, notes in array order), so the same inputs produce a byte-identical `bible.db`.

## Images (ADR-0012)

A note can carry a picture, such as a study Bible's chart. The picture is a file of its own, and
the note names it in `image`:

```
data/private/assets/<TRANSLATION>/chart-01.jpg
```

- One folder per translation, named by its exact id (`EMB`, not `emb`), holding only image files.
- Names are lower-case letters, digits, `-` and `_`, then `.jpg`, `.jpeg` or `.png`, at most 64
  characters before the extension.
- Only complete JPEG and PNG files are accepted, and the extension must match the content. Each is
  at most 2 MiB and 8,192 pixels a side.
- The bytes are baked into `bible.db` exactly as supplied and served at
  `GET /v1/translations/<TRANSLATION>/assets/<name>`.
- The build fails, naming the file, on anything else: an unknown translation folder, a sub-folder,
  a bad name, a wrong or truncated file.

Images are loaded before notes, so a note's `image` is checked against them.

## Why this is safe

The licensing safety is the **dual-ignore rule** (SPEC v4 §2): `data/private/` is excluded by
**both** `.gitignore` and `.dockerignore`. The Dockerfile's broad `COPY data/ data/` is *not*
selective — the `.dockerignore` exclusion is the only thing keeping restricted data out of the
build context and the baked `bible.db`. `data/private/notes/` and `data/private/assets/` sit under
that already-covered path, so they need no new ignore entry. Two tests enforce this:

- `test_notes_loader.test_clean_build_bakes_public_notes_but_zero_private_notes` — a build with
  no private data bakes zero private notes (the published-image behavior).
- `test_licensing_safety` — `data/private/` stays in both ignore files (the dual-ignore guard);
  a clean checkout bakes zero images; no image is committed under `data/`.

See [../../THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) and
[../../data/SOURCES.md](../../data/SOURCES.md) for the licensing record.
