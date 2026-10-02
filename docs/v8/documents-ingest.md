# Documents — ingest & user flow (Concord v8)

A study Bible prints more than notes. Some of what it prints is tied to a whole book or to no
verse at all: an introduction before each book, the front matter, a reading plan, notes about the
edition and its authors. Concord serves these as a translation's **documents**
([ADR-0012](../adr/ADR-0012-images-and-documents.md)): Markdown text under a slug, with links into
the Bible and the images the source prints.

Like the notes they sit beside, a study Bible's documents are **copyrighted and not
redistributable**. So Concord ships the *capability*, never the *data*: you supply documents from
a book you own, and they are baked into your **local** `bible.db`. The published image ships
**zero** documents.

> **Only load data you have the legal right to use.** Documents you place under `data/private/`
> are never committed and never baked into the published image — that is your responsibility to
> keep clean, and Concord's pipeline is built to make it automatic.

## The user flow

1. **Own the source.** For the Every Man's Bible, its converter writes the documents for you
   ([emb-ingest](emb-ingest.md)). For anything else, produce JSON matching the contract below by
   whatever means you legally can.
2. **Drop** the JSON at `data/private/documents/<TRANSLATION>.json`, one file per translation,
   and any images its text places at `data/private/assets/<TRANSLATION>/<name>`
   ([images](../v4/notes-ingest.md#images-adr-0012)). Both folders sit under the already
   gitignored and dockerignored `data/private/`, so nothing you put there can leak.
3. **Rebuild** Concord (`make build-db`, or `make docker-build-private` for your own image). The
   loader validates the documents and bakes them into your local `bible.db`. The build summary
   reports them:

   ```
   Built bible.db: 20 translations, …, 44 assets, 66 documents, … in 14.2s.
   ```

4. **Served.** `GET /v1/translations` shows each translation's `document_count`;
   `GET /v1/translations/<TRANSLATION>/documents` lists them (`?book=`, `?kind=`) and
   `GET /v1/translations/<TRANSLATION>/documents/<slug>` reads one ([API](../API.md)).

A build with no `data/private/documents/` (the public image, CI, any fresh clone) bakes **zero**
documents: every translation's list is empty, which is a normal state, not an error.

## The documents JSON contract

One file per translation. The loader (`bible_core.documents`) reads every `*.json` directly under
`data/private/documents/`.

```jsonc
{
  "translation": "EMB",              // REQUIRED — a loaded translation's code
  "documents": [
    {
      "slug": "introduction-gen",    // REQUIRED — lower-case letters, digits and "-" (starting
                                     //   with a letter or digit, at most 64), unique per translation
      "kind": "book-introduction",   // REQUIRED — front-matter | reading-plan | book-introduction
                                     //   | about
      "title": "A Made-up Title",    // REQUIRED — non-empty
      "book": "GEN",                 // a book introduction's book (code or any alias); REQUIRED
                                     //   for book-introduction, absent for every other kind
      "ordinal": 1,                  // REQUIRED — int >= 1, the document's place among its kind
                                     //   in print order; unique per (translation, kind)
      "text": "## A MADE-UP HEAD\n\nMade-up words on [chapters 1–3](ref:GEN.1-3).\n\n![A made-up caption](asset:figure-gen.jpg)"
                                     // REQUIRED — Markdown (CommonMark)
    }
  ]
}
```

- **Text is always Markdown.** Paragraphs, emphasis, lists, block quotes, headings, hard breaks.
- **Links into the Bible** are `ref:` links, `[words](ref:JHN.3.16)`, with the grammar notes use
  (ADR-0011): `BOOK.C`, `BOOK.C-C`, `BOOK.C.V`, `BOOK.C.V-V`, `BOOK.C.V-C.V`, each a known book.
- **An image** is placed with `![alt](asset:NAME)`, where NAME is one of the same translation's
  images. A client fetches it from the assets endpoint; a renderer that can't shows the alt text.
  `asset:` places images only: `[words](asset:…)` is refused.
- **A document's images** are read from its text, in order of first use, and served with its
  text (name, media type, width, height). There is nothing to list by hand.
- **One introduction per book** per translation.
- Unknown keys are ignored.

The build **fails loudly**, naming the file and the document, on: an unknown translation; a
missing or malformed field; a slug that isn't in the form above or is taken; a kind outside the
four; a book introduction without a book, a book on another kind, or a book that doesn't resolve;
a second introduction for one book; an ordinal taken within its kind; a `ref:` target outside the
grammar, naming an unknown book, or running backwards; an `asset:` image the translation lacks;
`asset:` used as a plain link.

The load is **idempotent**: document ids are assigned deterministically (files in sorted-path
order, documents in array order), so the same inputs produce a byte-identical `bible.db`.

## Why this is safe

The licensing safety is the **dual-ignore rule** (`docs/v4/SPEC.md` §2): `data/private/` is
excluded by **both** `.gitignore` and `.dockerignore`, and `data/private/documents/` sits under
it, so it needs no new ignore entry. Tests enforce the rest:

- `test_licensing_safety.test_private_data_dir_is_ignored` — `data/private/` stays in both ignore
  files.
- `test_licensing_safety.test_clean_checkout_bakes_zero_documents` — a build from a checkout with
  no `data/private/` bakes zero documents; the same build with a private documents file bakes it,
  so the zero isn't vacuous.
- `test_licensing_safety.test_clean_checkout_bakes_zero_assets` and
  `test_no_image_is_committed_under_data` — the same for the images a document places.

See [../../THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) and
[../../data/SOURCES.md](../../data/SOURCES.md) for the licensing record.
