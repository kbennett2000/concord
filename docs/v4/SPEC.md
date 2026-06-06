# Concord v4 — Translator's Notes (design spec)

Concord learns to **store and serve translator's notes** — the kind that make the NET Bible so
valuable: study notes, translator's notes, text-critical notes, anchored to specific points in
the verse text. This is a **Scripture-domain capability**, so it belongs in Concord (the
foundation), not in any app on top of it.

**The licensing reality drives the whole design.** The richest notes (NET) are copyrighted by
Biblical Studies Press, "all rights reserved," and are **not redistributable**. soap-journal
already proved the pattern: ship the *capability* and an MIT parser; the user supplies their own
legally-obtained data; the published artifact contains **zero** restricted content. Concord does
exactly this — and it already handles restricted *translations* this way (`data/private/`).
Translator's notes are the same shape: more data in the same private, never-published pipeline.

This is **Concord v4**. v1 (read API), v2 (semantic search), and v3 (geography) are shipped and
unchanged. songbird renders these notes in a **later songbird slice** (presentation over the new
endpoint) — out of scope here.

---

## 1. What this is (and is not)

**Is:** Concord gains a notes data model, an ingest path (from user-supplied parsed JSON), and a
read endpoint serving the translator's notes for a passage — including the note text, its type,
its anchor position in the verse, and its associated cross-references. Plus FTS over the notes.

**Is not:** a redistribution of any copyrighted notes (the published image ships none); a
note-*authoring* feature (these are translator's notes ingested from a source, not user-written
— user annotations are songbird's job); a span/range highlighter (the anchor is a point, §4);
the songbird UI (later). No new translations (notes attach to existing translations).

## 2. The boundary + the licensing invariant

- **Translator's notes are Scripture-domain → Concord owns the capability.** Apps consume it.
- **The published image ships ZERO copyrighted notes.** NET (and any restricted translation's
  notes) are **user-supplied** and loaded from `data/private/`, which is excluded from both the
  repo and the image.

> **NAMED INVARIANT — the dual-ignore rule (load-bearing):**
> Any directory holding copyrighted / non-redistributable data MUST be in **both `.gitignore`
> AND `.dockerignore`.** The Dockerfile's broad `COPY data/ data/` is **not** selective — the
> `.dockerignore` exclusion is the *only* thing keeping "all rights reserved" data out of the
> build context and the baked `bible.db`. This audit already confirmed `data/private/` is safe;
> v4 must not weaken it, and any new private path must be added to both files. Never assume the
> broad COPY is selective.

## 3. Architecture — bake into `bible.db` from the private pipeline

Notes are **baked into `bible.db`** by the loader at build time, from **user-supplied parsed
JSON in `data/private/`** — the same mechanism Concord already uses for restricted translations.

- A user who legally owns the NET Bible parses their PDF (reusing the **MIT-licensed NET parser**
  — the code ported from `kbennett2000/net-bible-study`, already used by soap-journal; not the
  copyrighted text) into the expected JSON, drops it in `data/private/`, and **rebuilds Concord
  locally** (the existing build). Their local `bible.db` then contains the notes.
- The **published GHCR image** is built with `data/private/` excluded (the dual-ignore rule), so
  it contains the public-domain translations and **no notes** — clean, exactly as today.
- This reuses the proven private-data pattern; **no new runtime-mount machinery**, no second
  database. Notes live in `bible.db` alongside verses (they reference verses by canonical
  coordinates anyway).

The result: **you** (with the NET PDF) get the full notes experience after a local rebuild; a
**stranger** pulling the public image gets the capability and loads their own legally-obtained
notes the same way. Concord's public image stays 100% redistributable.

## 4. Data model — soap-journal's proven schema (point anchors)

Mirror soap-journal's footnote model (it's proven and the parser already targets it). Notes
attach to a **verse + a single character offset** — a *point* anchor (an insertion point for a
superscript marker), **not** a character span. (This is finer than songbird's whole-verse
annotations but simpler than a range — a marker renders at a position.)

**`translator_notes`** (or `footnotes`):
- `id`
- canonical anchor: the verse it belongs to — **by canonical coordinates** (book USFM +
  chapter + verse) and/or a verse FK, consistent with Concord's coordinate model.
- `translation_code` — which translation the note set belongs to (NET today; notes are
  translation-specific, since the offset is into *that* translation's text).
- `note_type` — `tn` (translator's note) / `sn` (study note) / `tc` (text-critical) / `map`
  (constrained set; nullable/`other` for plain footnotes).
- `text` — the note body.
- `char_offset` — character offset into the verse text where the marker anchors (point anchor).
- `marker`, `ordinal` — source marker + stable render order within the verse.

**`note_cross_references`** — a note can carry cross-references: `note_id` → target canonical
coords (`to_book`, `to_chapter`, `to_verse_start`, `to_verse_end` nullable range). (Distinct
from Concord's TSK cross-references, which are verse→verse; these belong to a *note*.)

**FTS** — a notes FTS mirror (body + translation + note_type) so notes are searchable, matching
Concord's existing FTS approach for verses.

Scale (from the NET data): ~58k notes (tn ~47k, sn ~8k, tc ~2.5k, map ~0.6k), ~16k note
cross-references, ~33MB including the FTS index — tractable, baked into `bible.db` only when the
user supplies the data.

## 5. The endpoint(s)

Serve notes for a passage, in Concord's existing style (canonical coords, honest about
absence):

- **`GET /v1/translations/{translation}/notes/{book}/{chapter}`** (or `/{book}/{chapter}/{verse}`)
  — the translator's notes for the passage in that translation: each note's `type`, `text`,
  `char_offset` (so a client can place the marker), `marker`/`ordinal`, and its cross-references.
- A translation with **no notes loaded** (e.g. the public image, or any translation but NET) →
  an **empty result** (200, empty list), **not** a 404 — "this translation has no notes" is a
  normal, honest state, not an error. (A genuinely unknown translation → 404, per the existing
  split.)
- Consider **notes FTS search** exposure (e.g. `GET /v1/translations/{translation}/notes/search?q=`)
  — optional in the first slice; can follow. (songbird already searches its own annotations;
  searching *translator's* notes is a Concord capability.)

Endpoints return canonical coordinates throughout (notes anchored to verses; note cross-refs to
verses), so any consuming app overlays them by coordinate — same as everything else in Concord.

## 6. Ingest

- Reuse / adapt the **MIT NET parser** (from `net-bible-study` / as used by soap-journal) to
  produce the expected notes JSON from a user's NET PDF. The parser code is MIT and may live in
  Concord; the *output data* for NET is restricted and stays in `data/private/`.
- The **loader** (the existing `bible_core` loader that scans `data/` to build `bible.db`)
  learns to ingest notes JSON found alongside a translation in `data/private/` (and would ingest
  any future, differently-licensed annotated translation the same way).
- Document the user flow (a `data/private/README` or docs note): obtain your legal NET PDF →
  parse with the MIT parser → drop JSON in `data/private/` → rebuild Concord → notes are served.
  Mirror soap-journal's `bibles/README` honesty ("only load data you have the legal right to
  use").

## 7. What ships in the public image

- The **capability** (schema, loader support, endpoint, parser code) — yes.
- **Any copyrighted notes** (NET etc.) — **no.** The public image serves the endpoint, which
  returns empty for translations with no notes loaded. A puller loads their own licensed notes.
- `THIRD_PARTY_NOTICES` / docs updated to reflect: the parser is MIT; NET text/notes are
  copyrighted Biblical Studies Press and user-supplied, not redistributed.

## 8. Out of scope / deferred

- The **songbird UI** for notes (inline markers, hover/tap reveal — the soap-journal feel) — a
  later **songbird** slice over this endpoint.
- Span/range anchors (point anchor only, per the source data).
- User-*authored* notes (that's songbird annotations).
- Bundling any restricted data in the published image (forbidden — §2).
- Runtime-mountable notes DB (chose bake-into-`bible.db`; not building a mount system).
- New translations.

## 9. Definition of done (capability)

- Concord stores translator's notes (verse + `char_offset` point anchor, typed, with note
  cross-references and FTS), baked into `bible.db` by the loader from user-supplied JSON in
  `data/private/`.
- An endpoint serves a passage's notes (type, text, offset, marker, cross-refs) in canonical
  coordinates; a translation with no notes returns **empty (200)**, unknown translation → 404.
- The **published image ships zero restricted notes** and still runs clean/offline; the
  dual-ignore invariant (§2) holds (and any new private path is in both ignore files).
- The MIT parser path is documented; the user flow (parse → `data/private/` → rebuild) is
  documented; `THIRD_PARTY_NOTICES`/docs reflect the licensing.
- Existing v1/v2/v3 behavior unchanged.

## 10. Open questions (resolve in the slice plan)

1. **JSON shape + loader hook** — confirm the notes JSON schema (matching the parser's output /
   soap-journal's footnote fields) and exactly where the loader picks it up in `data/private/`
   (e.g. `data/private/<translation>/notes.json` or a flat file). Keep it consistent with how
   restricted translations are already loaded.
2. **Endpoint path + shape** — `/v1/translations/{t}/notes/{book}/{chapter}` vs. per-verse;
   the response object (how `char_offset`/`marker`/`ordinal` and the note cross-refs are
   returned so a client can render markers and follow refs).
3. **Notes FTS now or later** — include the notes search endpoint in the first slice, or land
   storage+passage-read first and add search next? (Lean: storage + passage-read first; search
   as a fast follow.)
4. **Parser home** — does the MIT NET parser live in Concord now (so the user flow is
   self-contained), or stay external/referenced? (Lean: bring the MIT parser into Concord so
   "parse → load" is one toolchain; the restricted *output* stays in `data/private/`.)
5. **Slicing** — likely two: (A) data model + loader ingest + the dual-ignore safety + tests
   (the foundation, gated like the map's projection slice); (B) the endpoint(s). Confirm.

### Resolutions (Slice V4-S1, 2026-06-06)

The open questions above were resolved in the foundation slice. Recorded here so the spec
tracks what shipped (see `docs/v4/notes-ingest.md` for the full contract + flow, and
`docs/dev-notes.md` V4-S1):

1. **JSON shape + pickup** — a Concord-native contract, one file per translation at
   **`data/private/notes/<CODE>.json`**. Notes live in a *subdirectory* of `data/private/`, so
   the non-recursive translation scanner never mistakes a notes file for a translation, and the
   existing `data/private/` ignore rule covers it (no new ignore path).
2. **FTS** — the `notes_fts` mirror is built **now** (in the loader); the search *endpoint* is
   deferred to a later slice.
3. **Parser home** — **deferred.** The MIT NET parser is external (`kbennett2000/net-bible-study`)
   and not yet vendored. Slice 1 is capability-first: it ingests against the documented JSON
   contract; the parser port is a follow-up.
4. **Verse anchor** — canonical coordinates (`book_id` + `chapter` + `verse`) + `translation_id`,
   no `verses.id` FK — matching `cross_references` / `place_verses`.
5. **Slicing** — confirmed two slices: **(1)** storage + ingest + licensing safety (this slice);
   **(2)** the read endpoint(s) + notes search.

### Resolutions (Slice V4-S2, 2026-06-06) — the §5 read endpoint

The passage-read endpoint shipped, serving the notes S1 baked. It mirrors `/cross-references`:

- **Endpoint:** `GET /v1/translations/{translation}/notes/{book}/{chapter}` with an optional
  `?verse=` to narrow to one verse (the chapter-path + optional-`?verse` granularity chosen at
  S1). One endpoint, both use cases.
- **Response shape:** a flat `notes` list, each note carrying its canonical anchor
  (`book`/`chapter`/`verse` + a `reference` string), `type`, `text`, `char_offset`, `marker`,
  `ordinal`, and a nested `cross_references` list (`to_book`/`to_chapter`/`to_verse_start`/
  `to_verse_end` nullable + `reference`). Top level echoes `translation`/`book`/`chapter`/`verse`
  + `total`. Ordered by `verse`, then `ordinal`, then id.
- **Honest absence (load-bearing):** a **known translation with no notes → 200 + empty list**
  (the published image ships zero notes, so it must return empty cleanly, not error). An
  **unknown translation → 404** (`unknown_translation`); an **unknown book → 404**
  (`unknown_book`, matching the chapter read). A valid-but-absent chapter/verse → empty 200
  (notes are an overlay, like `/verses/{ref}/places` — no verse-range validation). A non-positive
  `?verse` → 422 (edge validation).
- **Out of scope (a later slice):** notes FTS *search* exposure — `notes_fts` exists but is not
  queried by this endpoint.

## 11. Verification note (licensing-safe testing)

Tests must **not** depend on the copyrighted NET data being present (it's gitignored — CI won't
have it). Use a **tiny synthetic notes fixture** (a few fake notes in the JSON shape) to test
ingest + the endpoint + FTS, so the fast suite is licensing-clean and reproducible. Verifying
against the *real* NET notes is a local-only step (you have the PDF/JSON), reported like the
map's live-visual pass — never baked into CI or the image.
