# ADR-0012: a translation's images (and, in V8-S5, its documents)

**Status:** Accepted (images, V8-S4a). The documents part is appended by V8-S5.

<!--
Records how Concord keeps and serves a translation's images (docs/v8/SPEC.md §4.4, §5), settled in
slice V8-S4a before the EMB converter emits any (V8-S4b). Format mirrors ADR-0001..0011: Context /
Options / Decision / Consequences. V8-S5 adds a "Documents" part under the same number, as the
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
