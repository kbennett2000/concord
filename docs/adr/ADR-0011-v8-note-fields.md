# ADR-0011: v8 note fields, note types, `note_count` and `ref:` links

**Status:** Accepted

<!--
Records the notes contract the v8 private study Bibles need (docs/v8/SPEC.md §4.2, §5), settled
in slice V8-S2a before any converter emits it. Format mirrors ADR-0001..0010: Context / Options /
Decision / Consequences.
-->

## Context

v4 gave notes a deliberately small shape: a canonical anchor, a point `char_offset`, a coarse
`type` (`tn`/`sn`/`tc`/`map`/`other`), plain `text`, a `marker`, an `ordinal` and the note's own
`cross_references`. That fits NET, the only source so far.

The Every Man's Bible (v8) carries more, and songbird has to show it:

- **Kinds the coarse `type` can't name.** Textual notes and study notes map to `tn` and `sn`, but
  the five feature series ("Men, Women, and God", …) and the charts are neither. The reader needs
  the book's own name for each kind, and a coarse class to filter on.
- **Headings.** Features and charts have titles.
- **Formatting.** Study notes and features have paragraphs, italics, lists and quotations; flattened
  to plain text, they read badly.
- **Coverage.** A study note on Genesis 12:10–20, or a feature covering 12:10–20 *and* chapter 20,
  is anchored at one point but covers more than one verse.
- **Links in running text.** Notes cite other passages mid-sentence. `cross_references` lists
  references beside the text; it can't mark where in the text each one sits.
- **Charts are images.** That's the images slice (V8-S4), but the field belongs in this contract.

Songbird today (checked in its code) ignores response keys it doesn't know, shows note text as plain
text, labels `tn` "Translator's note" and `sn` "Study note", and turns `cross_references` into jump
buttons. So appended keys can't break it, and a source that doesn't use them keeps working unchanged.

## Options considered

- **(A) Append optional fields to the existing note object. Chosen.** This is ADR-0009's rule: a
  note gaining attributes of the thing it already represents is *completing* the object, not
  adding a feature. Every source uses one shape and one endpoint, and NET is untouched.
- **(B) A separate "features" table and endpoint for EMB's richer items.** Each EMB note would
  then live in one of two places by kind, and songbird would need a second reader for what is,
  to a reader, still a note on a passage.
- **(C) Encode the extras inside `text`** (a Markdown heading for the title, a prefix for the
  label). No schema change, but every client must parse conventions back out, and filtering or
  showing a label without the body becomes string surgery.

For **references inside text**, the options were:

- Concord's own reference strings (`John 3:16`): they contain spaces, which a CommonMark link
  destination can't hold unescaped.
- Full `/v1/verses/…` URLs: these tie stored data to a host and path.
- **A compact `ref:` target over USFM codes. Chosen.**

## Decision

**1. Fields.** These are appended to each note, after `cross_references` (the passage read) and
after `snippet` (the notes search), in this order:

| Field | JSON input | Response | Rule |
|---|---|---|---|
| `label` | optional string | string or `null` | The source's own name for the kind ("Textual Note", "Study Note", "Chart", …), for display. Non-empty after trimming. |
| `title` | optional string | string or `null` | The item's heading. Non-empty after trimming. |
| `text_format` | optional `"markdown"` | `"markdown"` or `null` | `"markdown"` when `text` is Markdown. Absent means plain text. No other value is accepted. |
| `passages` | optional list | list, `[]` when none | The canonical ranges the note covers beyond its anchor verse. Each entry is `{start_chapter, start_verse, end_chapter, end_verse}`, all integers ≥ 1, with the end not before the start. A range may cross chapters, and a note may have several. Ranges are **in the note's own book**. The response adds a `reference` string ("Genesis 12:10-20", "Genesis 12:10-13:4"). |
| `image` | must be absent or `null` | always `null` | Reserved for charts. The images slice (V8-S4) gives it a value and the check against stored images; until then the loader rejects any value, so no name can dangle. |

`type` stays the coarse class, and its set gains **`article`** (the feature series) and **`chart`**,
beside `tn`, `sn`, `tc`, `map` and `other`. The `?type=` filter on `/v1/notes/search` accepts both;
its 400 error lists the seven values with the original five first.

**2. `note_count`.** Appended to each `/v1/translations` entry: the number of notes loaded for that
translation, `0` when there are none. A client offers any translation with `note_count > 0` as a
notes source.

**3. `ref:` links.** Inside Markdown `text` (`text_format: "markdown"`), a reference a client can turn
into a jump is an inline link whose destination is `ref:` followed by a target:

```
[any display text](ref:TARGET)

TARGET  = BOOK "." C                      ref:JHN.3          whole chapter
        / BOOK "." C "-" C                ref:GEN.12-14      chapter range
        / BOOK "." C "." V                ref:JHN.3.16       single verse
        / BOOK "." C "." V "-" V          ref:JHN.3.16-18    verse range in a chapter
        / BOOK "." C "." V "-" C "." V    ref:JHN.3.16-4.2   cross-chapter range
BOOK    = a USFM book code as in docs/canonical-books.md: exact, upper case, no aliases
C, V    = a positive integer with no leading zero
```

- One book per target, and a range's end must not precede its start.
- Only the inline link form is defined: no reference-style links, no autolinks, and no `ref:` in
  plain-text notes.
- Every form maps one-to-one onto a reference `GET /v1/verses/{ref}` already accepts: replace the
  first `.` with a space and a chapter–verse `.` with `:`. So `JHN.3.16-4.2` becomes `JHN 3:16-4:2`,
  and `GEN.12-14` becomes `GEN 12-14`.
- The display text is free, so a link may read "v. 16" or "see chapter 20".

**4. Validation.** The notes loader fails the build loudly, naming the file, the note's index and
the bad value, on:
- a non-string or empty `label` or `title`;
- any `text_format` other than `"markdown"`;
- a malformed passage;
- a non-null `image`;
- in a Markdown note, any `ref:` target outside the grammar or naming an unknown book.

Notes are an overlay, as in v4, so passages and `ref:` targets aren't checked against a
translation's verse counts.

**5. OpenAPI.** The three affected endpoints (`/v1/translations`, the notes passage read and
`/v1/notes/search`) declare their response models with `responses={200: {"model": …}}`. So
`docs/openapi.json` records their bodies, new fields included, and `make openapi-check` guards
them. Runtime behaviour is unchanged: the handlers still return the cached raw response. This
narrows the gap ADR-0009 recorded for these three endpoints only; the rest stay undocumented
there, with `docs/API.md` as their field list. `docs/openapi.json` is rendered with sorted keys,
so it records which fields exist, not their order. The API tests pin the order.

## Consequences

- **No published key moves.** Clients reading the keys they know are unaffected. A note with none
  of the new fields (every NET note) returns them as `null`, `null`, `null`, `[]`, `null`.
- **Immutable caching hides the change from caches** (ADR-0009's caveat): a browser or proxy holding
  an old body can serve it without the new keys until it expires. Nothing has the fields until S2b
  loads EMB's notes, so the window costs nothing now.
- **Search snippets of Markdown notes carry raw Markdown**, link syntax included, because the full-
  text index reads `text` as stored. Clients use `text_format` to render or strip them. Search
  still indexes `text` only, not `title`; widening that is a separate change.
- **Passages stay within one book.** A note covering passages in two books would need a second note
  or a later, appended `book` field on passages. EMB's notes are per passage within a book, so
  none is known.
- **`ref:` targets are strict on purpose.** They're machine output from a converter, so the loader
  can reject anything off-grammar instead of guessing. Display text carries the human spelling.
- **`image` is a reservation.** A source can't set it yet; V8-S4 relaxes the check together with the
  table it points into.
