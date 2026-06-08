# Translator's notes — ingest & user flow (Concord v4)

Concord can **store and serve translator's notes** (NET-style study / translator's /
text-critical notes anchored to points in the verse text). Notes come from **two paths** that the
loader scans together (ADR-0004):

- **`data/notes/`** — **committed, public-domain** notes that **ship** in the published image. The
  World English Bible's own translator footnotes live here (`data/notes/WEB.json`): the WEB is
  public domain, so its notes are too. On a stock build, `GET /v1/translations/WEB/notes/{book}/{chapter}`
  returns these real footnotes.
- **`data/private/notes/`** — **user-supplied, restricted** notes that **never ship**. The richest
  source — the NET Bible — is **copyrighted by Biblical Studies Press, "all rights reserved," and
  is not redistributable.** So for restricted notes Concord ships the *capability*, never the
  *data*: you supply your own legally-obtained notes, and they are baked into your **local**
  `bible.db` only.

So the published image ships the committed **public-domain** notes (currently WEB's) and **zero
restricted** notes. Translations without any notes (public or private) simply return an empty list.

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

A build with no `data/private/notes/` (the public image, CI, or any fresh clone) bakes the
committed **public** notes (e.g. WEB's footnotes from `data/notes/`) and **zero private** notes —
the endpoint returns those public notes for WEB and an empty list for translations with no notes.

The WEB footnotes are derived from the public-domain eBible.org `engwebp` USFM by
[scripts/convert_web_footnotes.py](../../scripts/convert_web_footnotes.py) (footnotes only — not
verse text; verse-level anchor, `type` null, no cross-references for v1). See
[data/SOURCES.md](../../data/SOURCES.md) for provenance.

## The notes JSON contract

One file per translation. The loader (`bible_core.notes`) reads every `*.json` directly under each
notes directory — both `data/notes/` (committed, public) and `data/private/notes/` (local,
restricted) — scanned in that order and unioned.

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
      ]
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
- `note_type` is a **constrained set** (`tn`/`sn`/`tc`/`map`/`other`); omit it for a plain
  footnote (stored as `NULL`).
- The loader **fails loudly** (`LoaderError`) on malformed input: unknown translation, unknown
  book, bad note type, empty text, negative `char_offset`, or invalid JSON.
- The load is **idempotent** — note ids are assigned deterministically (files in sorted-path
  order, notes in array order), so the same inputs produce a byte-identical `bible.db`.

## Why this is safe

The licensing safety is the **dual-ignore rule** (SPEC v4 §2): `data/private/` is excluded by
**both** `.gitignore` and `.dockerignore`. The Dockerfile's broad `COPY data/ data/` is *not*
selective — the `.dockerignore` exclusion is the only thing keeping restricted data out of the
build context and the baked `bible.db`. `data/private/notes/` sits under that already-covered
path, so it needs no new ignore entry.

The **public** path `data/notes/` is the deliberate opposite: it is committed and **must NOT** be
ignored, so its public-domain notes ship (ADR-0004). Three tests enforce the split:

- `test_notes_loader.test_clean_build_bakes_public_notes_but_zero_private_notes` — a clean build
  (no `data/private/`) bakes the committed public notes but zero private notes.
- `test_licensing_safety.test_private_data_dir_is_ignored` — `data/private/` stays in both ignore
  files (the dual-ignore guard).
- `test_licensing_safety.test_public_notes_dir_is_not_ignored` — `data/notes/` stays OUT of both
  ignore files (the mirror guard, so the public notes never silently vanish from the image).

See [../../THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) and
[../../data/SOURCES.md](../../data/SOURCES.md) for the licensing record.
