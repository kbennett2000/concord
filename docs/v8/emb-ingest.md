# Every Man's Bible — ingest & user flow (Concord v8)

Concord can serve a **study Bible you own** as a private translation. The first one supported is
the **Every Man's Bible** (NLT second edition, `EMB`). Its text, notes and features are
**copyrighted by Tyndale House and the authors, "all rights reserved," and are not
redistributable** (`docs/v8/SPEC.md` §2). So Concord ships the *converter*, never the *data*:
you run it on your own copy, its output stays under `data/private/`, and it is baked only into
your **local** `bible.db`. The published image ships **zero** EMB content.

> **Only load data you have the legal right to use.** Everything the converter writes goes under
> `data/private/`, which is never committed and never baked into the published image — that is
> your responsibility to keep clean, and Concord's pipeline is built to make it automatic.

This page covers V8-S1: the **text** (verses and section headings). Notes, features, images,
documents and the Verse Finder follow in later slices (SPEC §7).

## The user flow

1. **Own the book.** The converter reads the PDF edition (a Calibre conversion of the Kindle
   book, 8,350 pages). The EPUB edition is optional and used only as a cross-check.
2. **Install poppler-utils** — the converter calls its `pdftohtml` (e.g.
   `sudo apt install poppler-utils`). Nothing else: the converter is standard-library Python
   plus `bible-core`, already in the repo's environment.
3. **Run the one command** from the repo root (about a minute):

   ```bash
   uv run python scripts/convert_emb.py --pdf "<your EMB.pdf>" --epub "<your EMB.epub>"
   ```

   `--epub` is optional but recommended: it is the only check of the text against a second
   witness. If `data/private/nlt.json` exists it is read as cross-check evidence only.
4. **Read the summary** it prints (below). If any check fails, nothing is written and the exit
   code is non-zero.
5. **Rebuild** Concord: `make build-db` for a local run, or `make docker-build-private` for your
   own Docker image (below). The build summary then counts one more translation.
6. **Served.** `EMB` appears in `GET /v1/translations` as "Every Man's Bible (NLT)" and reads
   through every existing endpoint; songbird lists it with no change.

The same PDF always gives byte-identical output, so re-running is safe.

## What the converter writes

| File | What |
|---|---|
| `data/private/EMB.json` | The translation: Concord's translation contract, code `EMB`, attribution read from the book's copyright page |
| `data/private/work/EMB/markers.json` | Where each removed `*` sat (book, chapter, verse, offset, where, target page, order) — the textual notes' anchors for V8-S2b |
| `data/private/work/EMB/crosscheck.tsv` | Every cross-check finding by reference and class (local only) |
| `data/private/work/EMB/summary.txt` | The printed summary |

No loader scans `data/private/work/`. Notes on the text:

- **Combined verses** (Numbers 1–2's census entries, printed "20-21") are stored under their
  first number; the absorbed numbers are absent, so a parallel read shows `null` for them.
  Verses the NLT omits (e.g. Matt 17:21) are absent the same way.
- **Psalm titles** begin verse 1, as in the other translations Concord carries.
- **Section headings** include Ps 119's stanza labels and Song of Songs' speaker labels. A
  heading the book prints inside a verse is attached before that verse (the summary lists them).
- **Tables** read as their rows, cells joined " - ".

## Reading the summary

- **Text** — counts against the S1 targets (✓ or ≠ target): 1,189 chapters, 31,064 verses,
  2,197 section headings + 59 labels, 4,817 `*` markers, 26 Perspectives boxes set aside.
- **Italic-only lines** — every italic line inside a chapter is claimed (title, verse text or
  label); **unclaimed must be 0**, or the run fails.
- **PDF quirks fixed** — counts of each fix (broken words, fractions, compounds, a table cell
  put back).
- **Checks** — the verse sequence against the public-domain KJV skeleton (with exactly the NLT's
  known omissions and extras), chapters against each book's own navigation list, and hygiene
  (no markup scraps, `*`, double spaces, broken words or fused headings). Any ✗ blocks the write.
- **Cross-check** (with `--epub`) — every verse where the PDF parse and the EPUB differ gets one
  class. The two that must be **0**: *fix regressions* (a fix broke a verse the raw parse had
  right) and *open, EPUB verse without damage*. Open items in visibly damaged EPUB verses are
  listed for reference.

## Getting your private data into your own Docker image

`.dockerignore` excludes `data/private/` — that is what keeps the published image clean, and it
stays. To bake your private translations into an image **for your own LAN only**, run one
command from the repo root:

```bash
make docker-build-private
```

It writes a temporary, untracked `Dockerfile.dockerignore` (`.dockerignore` without the
`data/private/` line), which BuildKit uses instead of the root one, runs `docker compose build`,
and deletes the file however the build ends — success, failure or Ctrl-C. The result is your
local `concord:latest`. Check it serves `EMB` before shipping it, and **never push that image** to
a registry; the command only builds.

**How long it takes.** The meaning-search embeddings depend only on the WEB verse text, the model
and the embedding code, so the Dockerfile gives them a stage of their own that sees nothing else
(V8-S1b). Measured on the build machine, 1 October 2026:

| What changed since the last build | Build | Embeddings |
|---|---|---|
| First build with this Dockerfile | 49 min (the embed alone 30–47 min, depending on the machine's load) | built |
| Anything under `data/private` (e.g. a re-run converter) | 52 s | reused |
| The converter (`scripts/emb_convert`, `scripts/convert_emb.py`) | 4 s | reused |
| bible-core or bible-api code | 75 s | reused |

The embeddings are rebuilt only when the WEB text, bible-semantic's code or pinned packages,
`scripts/fetch_model.py` / `scripts/build_embeddings.py`, or the base images change. The public
image build shares the same cached embeddings.

## Why this is safe

The licensing safety is the **dual-ignore rule** (`docs/v4/SPEC.md` §2): `data/private/` is
excluded by **both** `.gitignore` and `.dockerignore`, and every file the converter writes sits
under it. The converter itself holds no EMB text, and its tests use small synthetic
`pdftohtml -xml` fixtures with made-up text. Tests enforce the rest:

- `test_licensing_safety.test_private_data_dir_is_ignored` — `data/private/` stays in both
  ignore files.
- `test_licensing_safety.test_every_committed_dockerignore_excludes_private_data` — any committed
  `*.dockerignore` (which BuildKit would use in place of `.dockerignore`) keeps `data/private/`
  out; `test_private_build_ignore_file_is_gitignored` keeps the temporary
  `Dockerfile.dockerignore` out of git.
- `test_licensing_safety.test_clean_checkout_bakes_zero_private_translations` — a build from a
  checkout with no `data/private/` bakes only committed translations; a local `private/` is
  added, and its `work/` folder is never read as translations.

See [../../THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) and
[../../data/SOURCES.md](../../data/SOURCES.md) for the licensing record.
