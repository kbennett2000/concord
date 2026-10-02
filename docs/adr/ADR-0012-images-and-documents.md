# ADR-0012: a translation's images and documents

**Status:** Accepted (images, V8-S4a; documents, V8-S5a).

<!--
Records how Concord keeps and serves a translation's images (docs/v8/SPEC.md §4.4, §5), settled in
slice V8-S4a before the EMB converter emits any (V8-S4b). Format mirrors ADR-0001..0011: Context /
Options / Decision / Consequences. V8-S5a added the "Documents" part under the same number, as the
spec planned.
-->

## Context

A study Bible prints things that are pictures, not text. The Every Man's Bible has 44 charts whose
words are inside the image, and a reading-time figure in each book introduction. ADR-0011 gave
notes an `image` field for the charts, reserved and always null until this decision.

These images differ from everything else Concord serves:

- **They are bytes, not text.** A client needs the exact file and its media type to show one.
- **They are private.** A study Bible's charts are as copyrighted as its notes, so they come from
  the operator's own `data/private/`, never the repository or the published image (SPEC v8 §2).
- **They never change.** Like a verse, an image under a given name is immutable once built.
- **Concord runs offline from one baked artifact.** `bible.db` is built at image build time.
  Nothing is mounted or fetched at runtime.

## Options considered

- **(A) Store the bytes in `bible.db` and serve them from an endpoint. Chosen.** One baked
  artifact, as for every other dataset. The image build already copies `data/` into the builder, so a
  private build bakes the images with no Dockerfile change, and a public build bakes none.
- **(B) Files on a mounted volume, served as static files.** This adds a second artifact to keep
  in step with `bible.db` and a runtime mount to configure, and a missing file is only found when a
  client asks for it.
- **(C) Base64 inside the note JSON.** This bloats every notes response by a third more than the
  image, even for clients that never show it, and the image can't be cached apart from its
  chapter.
- **(D) Data URIs in Markdown text.** The same costs as (C), and plain-text clients would show the
  encoded bytes.

## Decision

**1. Table.** `translation_assets`: `translation_id`, `name`, `media_type`, `width`, `height` and
`bytes` (BLOB), unique on (`translation_id`, `name`). Rows hold the bytes exactly as supplied:
no re-encoding, no resizing.

**2. Loader.** `bible_core.assets` reads `data/private/assets/<CODE>/<name>` (the CLI's only
assets path). A missing folder loads nothing. The build fails, naming the file, when:

- `<CODE>` isn't a loaded translation, a file sits directly in `assets/`, or a sub-folder sits in
  `<CODE>/`;
- the name isn't lower-case ASCII letters, digits, `-` and `_` (starting with a letter or digit, at
  most 64 characters) followed by `.jpg`, `.jpeg` or `.png`;
- the bytes aren't a complete JPEG or PNG, sniffed from the content, or the extension disagrees
  with the content;
- the file is empty or over 2 MiB, or either side is over 8,192 px.

Width and height come from the header with `struct`: a JPEG's first frame header, a PNG's `IHDR`.
A JPEG must end with its end-of-image marker and a PNG with `IEND`, which catches a truncated
file. The image is never decoded, so `bible-core` stays standard-library only. Only JPEG and PNG
are accepted: SVG can carry script, and nothing needs GIF or WebP. Assets load before notes.

**3. The note's `image`.** ADR-0011's reservation is lifted. `image` is absent, `null`, or a
non-empty string naming an asset **of the note's own translation**. Anything else fails the build,
naming the file and the note. A note isn't required to have an image, and an asset isn't required
to be named by a note (V8-S5's documents will name some).

**4. Endpoint.** `GET /v1/translations/{translation}/assets/{name}`:

- `200`: the stored bytes with `Content-Type` set to the stored media type, a strong `ETag`
  derived from the bytes (the same hash as every JSON response), `Cache-Control: public,
  max-age=31536000, immutable`, `Vary: Origin` and, from the existing middleware,
  `X-Content-Type-Options: nosniff`. `If-None-Match` returns `304`.
- `404 unknown_translation` for a translation that isn't loaded (case-insensitive, as everywhere).
- `404 unknown_asset` for a name the translation lacks, whatever its shape, with `detail`
  `{translation, name}`. Names match exactly. An odd-looking name isn't a 422: there is simply no
  such image.

`docs/openapi.json` declares the `200` as `image/jpeg` or `image/png` binary.

## Consequences

- **`bible.db` grows by the images' bytes.** A JPEG is already compressed, so the Docker image and
  its gzipped tarball grow by about the same. EMB's 44 charts are 4.6 MiB.
- **Names are part of the contract.** A note stores a name, and a client builds the URL from it.
  A converter must keep its names stable for the same source.
- **Width and height are stored but not yet served.** S4 serves bytes only; a later field (V8-S5's
  documents list the images they use) can expose them without reading the bytes.
- **Older clients are unaffected.** A client that doesn't read `image` sees a chart as a note
  without its picture; one generated from `openapi.json` already types `image` as `string | null`.
  ADR-0009's caching caveat applies: a cache holding a chapter's notes from before a source added
  its charts can serve that body, without the charts, until it expires.
- **Licensing is unchanged in kind.** Images sit under the dual-ignored `data/private/`, and the
  licensing tests prove a clean checkout bakes zero assets and that no image is committed under
  `data/`.

---

# Documents (V8-S5a)

## Context

Everything a study Bible prints beside a verse is a note (ADR-0011). What is left is tied to a
whole book or to no verse at all:

- **Book introductions.** The Every Man's Bible prints one before each of its 66 books: sections
  under heads, links into the book, a timeline and a reading-time figure (an image).
- **Front matter** (the edition's introduction, contributors, the translation's preface), **a
  reading plan**, and **notes about the edition** (its authors and credits).

Like notes and images, these are private (SPEC v8 §2), never change once built, and must be read
offline from the one baked `bible.db`. A client needs to list them (for a book, or of a kind) and
read one, and its text links to passages and places images the translation carries.

## Options considered

Where documents live:

- **(A) A table baked into `bible.db`, served by two endpoints. Chosen.** One artifact, as for
  notes and images; a private build bakes them with no Dockerfile change, and a public build bakes
  none.
- **(B) Notes anchored at a book's 1:1.** A document isn't tied to a verse; an introduction would
  sit among chapter 1's notes, and front matter has no book at all.
- **(C) Files on a mounted volume.** The costs of images' option (B): a second artifact and a
  runtime mount, and a missing file found only when asked for.

How a document's text places an image:

- **(1) A CommonMark image whose target uses an `asset:` scheme, `![alt](asset:NAME)`. Chosen.**
  It mirrors `ref:` (ADR-0011): the text names the thing and the client builds the URL. Any
  Markdown renderer shows the alt text where it can't resolve the image.
- **(2) The API's URL in the text** (`/v1/translations/EMB/assets/…`). It ties stored text to
  one path prefix and one translation code, and a client behind another base path breaks.
- **(3) A placeholder token** (`{{image:NAME}}`). Invented syntax every client must strip.
- **(4) Images listed beside the text, not placed in it.** It loses where the book prints them.

## Decision

**1. Input.** `data/private/documents/<file>.json` (the CLI's only documents path), one file per
translation:

```jsonc
{ "translation": "EMB",
  "documents": [
    { "slug": "introduction-gen", "kind": "book-introduction", "title": "…", "book": "GEN",
      "ordinal": 1, "text": "## …\n\n…[Chapters 1–3](ref:GEN.1-3)…\n\n![…](asset:reading-time-gen.jpg)" } ] }
```

- `slug`: lower-case ASCII letters, digits and `-`, starting with a letter or digit, at most 64
  characters; unique within the translation.
- `kind`: `front-matter`, `reading-plan`, `book-introduction` or `about`.
- `title`: non-empty.
- `book`: required for a book introduction (any alias; stored as its USFM code), absent or null
  for every other kind. A translation has at most one introduction per book.
- `ordinal`: an integer ≥ 1, unique among the translation's documents of its kind — its place
  in print order. Per kind, so adding a kind never renumbers another.
- `text`: Markdown, always (CommonMark; no `text_format`). Its `ref:` links follow ADR-0011's
  grammar and name known books, as in notes. An image is placed with `![alt](asset:NAME)`, NAME
  an asset of the document's own translation (§ images above); `asset:` serves images only, never
  a plain link.

A document's **images** are read from its text, in order of first use — never supplied, so the
text and the list can't disagree. Unknown keys are ignored, as in notes. Documents load after
assets. Any violation fails the build, naming the file and the document.

**2. Tables.** `translation_documents` (`translation_id`, `slug`, `kind`, `title`, `book_id`,
`ordinal`, `text`), unique on (translation, slug) and (translation, kind, ordinal), `book_id` set
exactly for a book introduction, one introduction per (translation, book). `document_images`
(`document_id`, `position`, `name`).

**3. Endpoints.**

- `GET /v1/translations/{translation}/documents` → `{translation, book, kind, total, documents}`,
  each a summary `{slug, kind, title, book, ordinal}`. Order: by kind — front-matter,
  reading-plan, book-introduction, about, the order a study Bible prints them — then ordinal,
  then slug. `?book=` (any alias) keeps that book's introduction; `?kind=` one kind; together
  they combine. No paging: a translation has tens of documents.
- `GET /v1/translations/{translation}/documents/{slug}` → `{translation, slug, kind, title, book,
  ordinal, text, images}`, each image `{name, media_type, width, height}` — the width and height
  §1 stored, so a client can lay out a figure before fetching its bytes from the assets endpoint.
- Honest absence: a known translation with no documents, or filters matching none → `200` and an
  empty list. An unknown translation → `404 unknown_translation`; a slug the translation lacks →
  `404 unknown_document`, `detail` `{translation, slug}` (exact match, as asset names). An unknown
  `?book=` → `400 unknown_book`, an unknown `?kind=` → `400 unknown_kind` with `available`: closed
  filters, as `/v1/notes/search`'s `?type=`.
- Both carry the immutable caching of every read: a strong ETag, `Cache-Control: public,
  max-age=31536000, immutable`, `Vary: Origin`, `304` on `If-None-Match`.
- `GET /v1/translations` gains `document_count` on each entry, appended after `note_count`
  (ADR-0009).

## Consequences

- **Older clients are unaffected.** No existing response changes shape; `/v1/translations` only
  appends `document_count`. ADR-0009's caching caveat applies: a cache holding that body from
  before can serve it, without the count, until it expires. A client that renders a document with
  a notes renderer shows each figure's alt text.
- **Slugs and asset names are part of the contract.** A client stores and links them, so a
  converter keeps both stable for the same source.
- **`bible.db` grows by the text** (and the images, counted under images). Documents aren't
  searched: no FTS index, and `/v1/notes/search` doesn't see them.
- **Licensing is unchanged in kind.** Documents sit under the dual-ignored `data/private/`, and
  the licensing tests prove a clean checkout bakes zero of them.
