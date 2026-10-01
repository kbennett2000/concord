# Concord v8 — Private study Bibles Build Spec

**Concord v8** lets an operator load a **study Bible they own** — its translation text and everything printed around it — and serve all of it through Concord's read API, kept private like NET's notes. The first source is the **Every Man's Bible** (`EMB`, "Every Man's Bible (NLT)"): the NLT second-edition text with its textual notes, study notes, five feature types, charts, book introductions, front matter, reading plan and the Tyndale Verse Finder.

This spec sits beside `docs/v4/SPEC.md` (translator's notes) and ADR-0004 (public + private notes paths). v8 is **purely additive**: optional fields appended to notes (ADR-0009's rule), two new tables (documents, images), a second topics path, and a few endpoints. No new package, no ML. The `/v1` prefix stays.

---

## 1. Goals & shape

After v8, an operator's local build with the EMB data in `data/private/` serves:

- **The text.** `EMB` is a translation — verses and section headings — read through every existing endpoint. songbird shows it with no change.
- **Everything tied to a verse or passage, as notes on `EMB`:** the textual notes (the NLT footnotes behind each `*`), the study notes, the five features — Men, Women, and God; Someone You Should Know; What the Bible Says About; Perspectives; Personal Gold — and the charts. Each carries its label, its title, the passages it covers, Markdown text and (charts) an image.
- **Everything tied to a whole book or to no verse, as documents of `EMB`:** the 66 book introductions (each with its What's the Point line, timeline and reading-time figure), the front matter (copyright page, Introduction to the Every Man's Bible, Contributors, Introduction to the NLT, the NLT translation team), the Personal Gold author notes and credits, and the One Year Reading Plan (365 days × 4 readings, each reading a reference a client can link).
- **The Tyndale Verse Finder as a second topical source**, served by the existing `/v1/topics*` endpoints beside Nave's and marked with its source.
- **Images** (charts, reading-time figures) baked into `bible.db` and served by Concord.

Not copied: the book's indexes and contents pages. They are navigation; a client rebuilds them from the data.

## 2. The licensing invariant (unchanged)

- The NLT text (© Tyndale House Foundation), the EMB notes (© 2004 Stephen Arterburn and Dean Merrill) and the Tyndale Verse Finder (© 2000 Tyndale House Publishers) are all rights reserved. Tyndale's free-quotation limit (500 verses, under 25% of a work, no complete book) rules out shipping any of it.
- So **every EMB output lives under `data/private/`**, dual-ignored (`docs/v4/SPEC.md` §2). The new private paths — `data/private/documents/`, `data/private/assets/`, `data/private/topics/` — sit under it, so no ignore file changes. The licensing tests grow with each slice to prove a clean build bakes **zero** private documents, images and topics.
- **CI stays hermetic:** tests use tiny synthetic fixtures with made-up text. No EMB text in the repo — not in tests, fixtures, docs or dev-notes. Verse references and counts are fine.

## 3. The source — measured, not assumed

A measuring-only session (1 Oct 2026) compared Kris's two files. Both are Calibre conversions (21 Apr 2014) of the same Kindle edition (ASIN B008847REW).

- **The PDF is the source.** 8,350 single-column e-reader pages, a real text layer, every internal link intact, an 81-entry outline. All 10 spots checked where the EPUB is damaged read correctly in it. Read it with `pdftohtml -xml` (poppler-utils): font size, colour and link targets carry the structure. Charts are its embedded 1,024 px JPGs.
- **The EPUB is not a source.** Its conversion dropped and fused words and left markup scraps in about one verse in nine; 3,189 verses disagree with the PDF, 936 of them with no visible sign. It serves only as an independent cross-check of the PDF parse.
- **No clean second-edition reference text exists locally.** Kris's private `NLT` is the 1996 first edition (73% of verses word differently). So the verse text is proven by cross-check: PDF vs EPUB, every disagreement classified (S1's classes: fixed PDF quirk, fix regression, EPUB damage, EPUB splice, EPUB loss with evidence at the spot, hyphenation variant, verified on the rendered page, open). S1's result: 25,500 verses agree, 0 fix regressions, 0 open where the EPUB verse shows no damage.
- **PDF quirks the converter must handle** *(as measured by S1)*:
  - **Words broken by spacing** — 300 items in 275 verses (not "~90"). Justification spreads the last word of a verse, first on its line before the next verse number, glyph by glyph or once ("g o o d .", "prophes y."); the italic font does the same mid-line in psalm titles. Joined only where the pieces make a known word and are not themselves words.
  - **Hyphens** — no line-end hyphen is dropped. The "~70" were compounds the PDF *prints* closed (rendered and checked): 28 verses keep a valid closed spelling as printed ("cupbearer", "coworker"); one compound prints fused in 23 verses ("fatherin-law") and is repaired from the PDF's own evidence. A hyphen or em dash at the end of a *wrapped* prose line closes up; at a poetic line break it keeps its space.
  - **Small caps** — 7,151 "L"+"ORD" fragments, plus small-caps phrases (inscriptions, Paul's signature lines), set at verse-number size.
  - **Fractions** — 146, printed as small "1" "/" "2" after a digit; stored as ½ etc.
  - **Combined verses** — 24 entries in Numbers 1–2 printed as a range ("20-21"), absorbing 24 verse numbers (the measurement counted both numbers of each, 48).
  - **Tables** — 15 table runs in Num 1, 2, 13, 34; 1 Chr 27; Ezra 1, 2; Neh 7; Rev 7. Cells are joined " - " (the operator's NLT's own format for Num 1–2), rows in one verse by a space, header rows ("Tribe / Leader") dropped. One row is split across a page (Num 1:6–7) and is put back.
  - **Explicit chapter turns** — Dan 11:1, Hos 2:1 and 1 Cor 11:1 are printed "11:1" before their chapter's header.
  - **Never part of a verse** — 26 Perspectives text boxes, feature callout labels (266 lines), book introductions and chapter-navigation lists.
- **Verse count:** **31,064** = the 31,102-verse skeleton − 24 numbers absorbed by combined entries − 16 verses the NLT omits (e.g. Matt 17:21) + 2 the NLT's versification adds (3 John 1:15, Rev 12:18). The measurement's 31,040 dropped both numbers of each combined entry; the "14 Hosea verses" do not exist (Hosea parses complete).
- **Measured inventory — the converter's acceptance targets:**

| Item | PDF count | Tied to |
|---|---|---|
| Chapters / verse numbers | 1,189 / 31,064 (S1; measured 31,040) | — |
| Section headings | 2,197 (S1; measured 2,206 bold-italic lines incl. 9 table header rows), plus 59 labels as headings (22 Ps 119 stanzas, 37 Song of Songs speakers) | before a verse |
| Textual notes | 4,827 in 958 chapter blocks (4,817 `*` markers) | a verse; 859 split a/b |
| Study notes | 2,467 | 2,035 ranges · 332 verses · 52 cross-chapter · 33 multi-part · 15 whole chapters |
| Men, Women, and God | 99 articles, 101 callouts | 55 ranges · 30 whole chapters · 8 multi-part · 5 verses · 1 cross-chapter |
| Someone You Should Know | 94, 94 callouts | a passage; ~1 in 4 crosses chapters |
| What the Bible Says About | 51 topics (503 quoted verses), 50 callouts | a topic; callout at one verse |
| Perspectives | 26 text boxes | 12 ranges · 10 verses · 3 multi-part · 1 whole chapter |
| Personal Gold | 24 articles, 24 callouts | 20 ranges · 4 verses |
| Charts | 44 images | 30 ranges · 7 cross-chapter · 6 verses · 1 whole chapter |
| Book introductions | 66 (11 section types, 3 sometimes absent; timeline; What's the Point; one image each) | whole book |
| Banner images | 102, above feature articles | — |
| Front matter | copyright, EMB intro, Contributors, NLT intro, NLT team | — |
| Verse Finder | 191 pages, topic → references | topics |
| One Year Reading Plan | 365 days × 4 readings (1,460 references) | — |

## 4. Data model (all additive)

**4.1 Text — `data/private/EMB.json`.** The existing translation contract, unchanged: code `EMB`, name `Every Man's Bible (NLT)`, language `en`, `copyright` = the book's own copyright-page lines. `*` markers are removed from verse text; their positions become textual-note offsets (S2) — S1 records them in `data/private/work/EMB/markers.json` (book, chapter, verse, offset, where: verse / title / heading / chapter, target page, order in chapter; 4,817). A combined verse is stored under its first number and the other numbers are absent (honest absence: `null` in parallel reads). As S1 settled:
- **Psalm titles** are prefixed to verse 1, as in WEB, KJV, ASV, BSB, JPS, YLT, ESV and NKJV, so parallel reads line up.
- **Ps 119's stanza labels and Song of Songs' speaker labels** are section headings (editorial, not Scripture). Interlude, refrains and italic book titles stay verse text.
- **Mid-verse headings** (23, e.g. Gen 2:4, Obad 1:1, five Song of Songs speaker labels) attach before the verse they interrupt: `before_verse` has no mid-verse position, so a speaker label can sit above words the previous speaker says. A known limit of the headings contract.
- **Tables** — cells joined " - ", header rows dropped (§3).

**4.2 Notes — `data/private/notes/EMB.json` (ADR-0011, S2).** The v4 contract plus appended, optional fields:
- `label` — the source's own name for the kind ("Textual Note", "Study Note", "Men, Women, and God", …, "Chart"). Clients show it; `type` stays the coarse class.
- `title` — the item's heading, where it has one.
- `text_format` — `"markdown"` when `text` is Markdown (paragraphs, italics, bold, lists, quotes); absent means plain text (NET is unchanged).
- `passages` — the canonical ranges the note covers, when that is more than its anchor verse. A note on "Genesis 12:10-20 and chapter 20" has two.
- `image` — an image name (§4.4), for charts.
- The `type` set gains `article` (the five features) and `chart`. Textual notes are `tn`, study notes `sn`.
- **Where the marker goes:** a textual note at its `*`; a study note at the start of its first verse; a feature or chart where the book puts its callout. A feature the book calls out more than once shows at each callout; one it never calls out anchors at the start of its first passage (S3's plan checks both against the data). References the book links inside a note become `cross_references`, or `ref:` links in the Markdown (grammar in ADR-0011).

**4.3 Documents — `data/private/documents/EMB.json` (ADR-0012, S5).** New table `translation_documents`: `slug`, `kind` (`book-introduction`, `front-matter`, `reading-plan`, `about`), `title`, `book` (book introductions only), `ordinal`, Markdown `text`, and the image names it uses. References inside the text are `ref:` links.

**4.4 Images — `data/private/assets/EMB/` (ADR-0012, S4).** New table `translation_assets`: `name`, `media_type`, `width`, `height`, `bytes` — baked into `bible.db` like everything else (no runtime mount). The slice reports the `bible.db` size change. The 102 banner images above feature articles are decorative unless S3 finds one carrying words that aren't in the text layer; decorative ones aren't copied (the note's `label` replaces them).

**4.5 Verse Finder — `data/private/topics/` (ADR-0013, S6).** The topics loader scans `[data/topics, data/private/topics]` (ADR-0004's pattern). Same topics contract; `source` = "Tyndale Verse Finder"; ids prefixed `vf-`; ranges expand to their verses.

## 5. Endpoints (appended fields per ADR-0009, plus new paths)

- `GET /v1/translations` — each entry gains `note_count` (S2) and `document_count` (S5). songbird offers any translation with `note_count > 0` as a notes source.
- `GET /v1/translations/{t}/notes/{book}/{chapter}` and `GET /v1/notes/search` — notes gain the §4.2 fields (null or empty when absent). Paths unchanged.
- `GET /v1/translations/{t}/documents` (`?book=`, `?kind=`) — summaries. `GET /v1/translations/{t}/documents/{slug}` — one document. (S5)
- `GET /v1/translations/{t}/assets/{name}` — the image bytes, their content type, an immutable ETag. (S4)
- `GET /v1/topics*` — topics gain `source`; `/v1/topics` gains `?source=`. (S6)
- Honest absence as everywhere: a known translation with none → `200` and an empty list; an unknown translation, slug or image → `404`.

## 6. The converter

- MIT code in this repo that reads **the operator's own PDF** and writes the §4 files under `data/private/`. It holds no EMB text. One command regenerates everything; the same PDF gives byte-identical output.
- Lives outside `bible-core`, `bible-api` and `bible-semantic` (none import it) and adds no runtime dependency. Ruff- and Pyright-strict-clean, tested on synthetic `pdftohtml -xml` fixtures. **Placement (S1):** the `scripts/emb_convert/` package behind `scripts/convert_emb.py` (beside the other `convert_*` scripts), tests in `scripts/tests/`; standard library plus `bible_core.seed`, and `pdftohtml` at convert time only. One command: `uv run python scripts/convert_emb.py --pdf <EMB.pdf> [--epub <EMB.epub>]` (≈1 minute). The cross-check is a converter option (`--epub`), so it re-runs whenever a later slice changes the converter; the operator's private NLT, when present, is evidence only. User flow: `docs/v8/emb-ingest.md`.
- Every run prints a **verification summary**: counts per item against §3's table and, given the EPUB, the PDF-vs-EPUB verse cross-check with every disagreement classified.
- The user flow is documented the way `docs/v4/notes-ingest.md` documents NET's: own the book → run the converter → rebuild → served. Only load data you have the legal right to use.

## 7. Build plan — sliced for Claude Code

Each slice ends with Kris able to use the result. songbird's matching slices (its own spec) are shown where they slot in.

| # | Slice | Delivers | Usable result |
|---|---|---|---|
| V8-S1 | The text | This spec; the converter foundation; `EMB.json` (verses + headings); the PDF-vs-EPUB cross-check; the user-flow doc; EMB live in Kris's Concord | EMB in songbird's translation menu, reading cleanly |
| V8-S2 | Textual + study notes | ADR-0011 (§4.2 fields, two new types, `note_count`); the converter emits textual and study notes | EMB's footnotes and study notes in songbird's reader |
| songbird A | Notes from any source | Per-translation "show notes from" choices replacing the NET-only checkbox (an existing NET choice is kept); labels, titles, passages, Markdown | EMB notes on every other translation, like NET's |
| V8-S3 | Features | The converter emits the five feature types | Features in the reader, on any translation |
| V8-S4 | Images + charts | ADR-0012 (images): table, endpoint; charts and reading-time figures | Chart notes resolve to images |
| songbird B | Charts | Images in the note view | Charts in the reader |
| V8-S5 | Documents | ADR-0012 (documents): table, endpoints; book introductions, front matter, Personal Gold authors, reading plan | — |
| songbird C | Introductions + About | A book's introduction from the reader; an About page for this Bible (front matter, reading plan); `ref:` links jump to the reader | Book intros, front matter and reading plan in songbird |
| V8-S6 | Verse Finder | ADR-0013: private topics path, `source`, `?source=` | — |
| songbird D | Topics by source | The Topics page and verse topics show the source, with a filter | Verse Finder beside Nave's |
| V8-S7 | Release | README, `docs/API.md`, OpenAPI, version bump, release notes | Published image — still zero EMB content |

## 8. Out of scope

- Shipping any EMB content (§2).
- Searchable chart text (it is inside the images; no OCR).
- A reading-plan tracker (the plan is a readable document — Kris's call, 1 Oct 2026).
- The EPUB as a data source.
- Kris's private `NLT` file (its Hosea 2–14 is broken — a separate item).

## 9. Acceptance

v8 is done when, on Kris's machine: songbird shows "Every Man's Bible (NLT)" with clean text; every §3 count is met or each difference explained; every note type, chart, document and Verse Finder topic is reachable in songbird; EMB notes show on other translations; and a clean build (no `data/private/`) bakes zero EMB content, proven by tests.
