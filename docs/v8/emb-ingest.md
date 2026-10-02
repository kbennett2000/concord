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

This page covers the **text** (verses and section headings, V8-S1), the **textual and study
notes** (V8-S2b), all five **features**: the articles the text calls out at a passage — Men,
Women, and God; Someone You Should Know; Personal Gold (V8-S3a) — and What the Bible Says About
and Perspectives (V8-S3b), the **charts** with their images (V8-S4b), the 66 **book
introductions** with their reading-time figures (V8-S5b), and the **front matter**, the **One
Year Reading Plan** and **Personal Gold's author notes and credits** (V8-S5c), as documents. The
Verse Finder follows in a later slice (SPEC §7).

## The user flow

1. **Own the book.** The converter reads the PDF edition (a Calibre conversion of the Kindle
   book, 8,350 pages). The EPUB edition is optional and used only as a cross-check.
2. **Install poppler-utils** — the converter calls its `pdftohtml` (e.g.
   `sudo apt install poppler-utils`). Nothing else: the converter is standard-library Python
   plus `bible-core`, already in the repo's environment.
3. **Run the one command** from the repo root (under two minutes):

   ```bash
   uv run python scripts/convert_emb.py --pdf "<your EMB.pdf>" --epub "<your EMB.epub>"
   ```

   `--epub` is optional but recommended: it is the only check of the text and the notes
   against a second witness. If `data/private/nlt.json` exists it is read as verse cross-check
   evidence only.
4. **Read the summary** it prints (below). If any check fails, nothing is written and the exit
   code is non-zero.
5. **Rebuild** Concord: `make build-db` for a local run, or `make docker-build-private` for your
   own Docker image (below). The build summary then counts one more translation, EMB's notes,
   its 110 images (assets: 44 charts and 66 reading-time figures) and its 73 documents (66 book
   introductions, 5 front-matter pieces, the reading plan and Personal Gold's authors).
6. **Served.** `EMB` appears in `GET /v1/translations` as "Every Man's Bible (NLT)", with its
   `note_count`, and reads through every existing endpoint; its notes through
   `/v1/translations/EMB/notes/{book}/{chapter}` and `/v1/notes/search`; a chart's image through
   `/v1/translations/EMB/assets/{name}`, the name its note gives in `image`; the documents
   through `/v1/translations/EMB/documents` (`?book=`, `?kind=`) and
   `/v1/translations/EMB/documents/{slug}` ([documents-ingest](documents-ingest.md)).

The same PDF always gives byte-identical output, so re-running is safe.

## What the converter writes

| File | What |
|---|---|
| `data/private/EMB.json` | The translation: Concord's translation contract, code `EMB`, attribution read from the book's copyright page |
| `data/private/notes/EMB.json` | Its textual and study notes, its five features and its charts: the notes contract (`docs/v4/notes-ingest.md`, ADR-0011) |
| `data/private/documents/EMB.json` | The 66 book introductions, then the front matter, the reading plan and Personal Gold's authors: the documents contract (`docs/v8/documents-ingest.md`, ADR-0012) |
| `data/private/assets/EMB/chart-01.jpg` … `chart-44.jpg` | Each chart's image, exactly as the PDF stores it, numbered in the book's order (ADR-0012) |
| `data/private/assets/EMB/reading-time-gen.jpg` … | Each introduction's reading-time figure, exactly as the PDF stores it, named by its book |
| `data/private/work/EMB/markers.json` | Where each removed `*` sat (book, chapter, verse, offset, where, target page, order) — the textual notes' anchors |
| `data/private/work/EMB/crosscheck.tsv` | Every verse cross-check finding by reference and class (local only) |
| `data/private/work/EMB/notes-crosscheck.tsv` | Every note cross-check finding by note and class (local only) |
| `data/private/work/EMB/articles-crosscheck.tsv` | Every article cross-check finding by feature, passage and class (local only) |
| `data/private/work/EMB/topics-crosscheck.tsv` | Every topic and box cross-check finding by feature, topic number or box passage, and class (local only) |
| `data/private/work/EMB/charts-crosscheck.tsv` | Each chart's index entry and image against the EPUB's (local only) |
| `data/private/work/EMB/introductions-crosscheck.tsv` | Every introduction finding by book, section and class (local only) |
| `data/private/work/EMB/documents-crosscheck.tsv` | Every other document's finding by piece and section, plan day, author note or credit, and class (local only) |
| `data/private/work/EMB/summary.txt` | The printed summary |

No loader scans `data/private/work/`. Notes on the text:

- **Combined verses** (Numbers 1–2's census entries, printed "20-21") are stored under their
  first number; the absorbed numbers are absent, so a parallel read shows `null` for them.
  Verses the NLT omits (e.g. Matt 17:21) are absent the same way.
- **Psalm titles** begin verse 1, as in the other translations Concord carries.
- **Section headings** include Ps 119's stanza labels and Song of Songs' speaker labels. A
  heading the book prints inside a verse is attached before that verse (the summary lists them).
- **Tables** read as their rows, cells joined " - ".

Notes on the notes:

- **Textual notes** (`tn`, label "Textual Note") are the NLT footnotes behind each `*`, each
  attached where its `*` sat: in the verse text, inside a psalm title (verse 1), at the start of
  a chapter whose header carries the `*`, or by a heading's `*` (SPEC §4.2).
- **Study notes** (`sn`, label "Study Note") attach at the start of the verse where the book
  calls them out, and list every passage their heading names.
- **Text** is Markdown (`text_format: "markdown"`) only when a note has italics or links: italics
  as `*…*`, the book's own `[`, `]` and other Markdown characters escaped, and each reference the
  book links as a `ref:` link (ADR-0011). Other notes are plain text.

Notes on the feature articles (`article`, labelled with the feature's name; SPEC §4.2):

- **Title** is what the book's own index calls the article. The passage it covers is `passages`
  (in the note's book; a second book's parts go to `cross_references`).
- **Where it attaches:** where the book calls it out. Men, Women, and God and Personal Gold call
  an article out after its passage, so the note sits at the end of the passage's last verse;
  Someone You Should Know calls it out before, so the note sits at the start of the first verse
  (three callouts stand in book introductions: verse 1:1). At its verse an article shows before
  the other notes when it opens a passage, after them when it closes one.
- **Text** is always Markdown: paragraphs, bold lead-ins, set-off blocks as quotations, the
  book's lists (`- `, numbered), verse quoted line by line with hard breaks, headings shown bold,
  a source note's number as a superscript. Personal Gold's text opens with "from" and the author.
  The banners above Men, Women, and God articles are one decorative image (its only words are
  the feature's name, the label) and are not copied.

Notes on What the Bible Says About and Perspectives (`article`, labelled with the feature's name;
SPEC §4.2):

- **A topic** is a page of quoted verses under subheads. Its title is what the book's index calls
  it; its text keeps each subhead (a heading, shown bold), each quotation as printed (poetic
  lines on lines of their own) and the quotation's reference as a link under it. It attaches at
  the end of the verse where the book calls it out, and lists no passages: every verse it quotes
  is a link in its text.
- **A Perspectives box** stands inside the Bible text. Its note holds the passage it quotes, that
  passage's reference as a link, the saying and the attribution, as printed (no title: the box
  prints none). It attaches at the end of the verse the box follows, and its passages are the
  reference the box prints.
- Where a topic or box shares a verse end with a Men, Women, and God article, it shows in the
  book's order, and the verse's earlier notes keep their numbers.

Notes on the charts (`chart`, labelled "Chart"; SPEC §4.2, §4.4):

- **A chart is a picture.** Its words are inside the image, so the text layer holds no title
  for it. The book's Charts Index lists every chart: a title linking to the chart's page, then
  its passage in parentheses.
- **Title and passage** come from that index. The note's text is the passage as the index
  prints it, as a `ref:` link: a client with no picture still has the title and a jump to the
  passage.
- **The image** is copied byte for byte from the PDF (no re-encoding) into
  `data/private/assets/EMB/`, and the note names it in `image`. The converter refuses to write
  when that folder holds a file it wouldn't write, so a stale image can't be baked in.
- **Where it attaches:** the end of the verse the image follows (S3a's rule), after the verse's
  other notes, so their numbers don't move. Most charts close their passage; a few stand inside
  it or just after it, and the summary lists them.
- **The book's other images aren't copied**: the callout icons and the Men, Women, and God
  banner (their only words are the feature's name, which the label carries), the testament title
  pages and the cover. The reading-time figures come with the introductions (below).

Notes on the book introductions (documents, `kind` `book-introduction`; SPEC §4.3, §4.4):

- **One document per book**, slug `introduction-<book>` (`introduction-gen`), ordered by the
  book's place, titled with the book's name. Its text is what the book prints between the book's
  navigation page and its first chapter, as Markdown: each section head (`##`, capitals as
  printed), the sections' paragraphs and one-entry-per-line lists, the bold labels over a
  quotation (a block quote; poetry line by line) or over a few paragraphs, the What's the Point
  heading and line, and the timeline (a list: each date, then its event in bold).
- **Every reference the book links** is a `ref:` link (the chapter ranges a book outlines, the
  passages to memorize, references in the text), checked against the book's own link targets.
- **The reading-time figure** is a picture: the reading time is inside it, not in the text. It
  is copied byte for byte into `data/private/assets/EMB/reading-time-<book>.jpg` and placed in
  the text where the book prints it, `![caption](asset:reading-time-<book>.jpg)`, the caption
  printed above it as its alt text. A client that can't show images shows the caption.
- **Not part of an introduction:** the navigation page, the three Someone You Should Know callout
  lines that stand at an introduction's end (their articles attach at verse 1:1), and the heading
  printed above the first verse (it belongs to the text).
- **Topic titles:** three What the Bible Says About titles the index sorts with "The" last read in
  normal word order since V8-S5b.

Notes on the front matter, the reading plan and Personal Gold's authors (documents; SPEC §4.3):

- **The front matter** is five documents, `front-matter-1` … `front-matter-5`, in the book's
  order: the copyright page (titled "Copyright": the book prints no title on it), then each
  section the book's outline lists before the Verse Finder, titled as the outline names it.
  Each is read by its layout: paragraphs and their one-per-line lists; heads, paragraphs,
  bulleted items (an item's own further paragraph stays inside it) and the signature; centred
  roles over their names; a team's divisions, groups and people, one per line. Every reference
  the book links is a `ref:` link. The contents pages and the cover are not copied: a client
  builds its own contents from the documents.
- **The reading plan** is one document, `reading-plan-1`: each day a heading (the date as
  printed) over its four readings, each a `ref:` link a client can open. A reading that runs on
  into the next book is two links, the text unchanged; a reading ending on part of a verse
  ("…a") links the whole verse. The plan's month list is navigation and isn't copied.
- **Personal Gold's authors** is one document, `about-1`: the author index's notes as printed
  (each author's name in bold), then the Personal Gold index's entries — each excerpt's title,
  its author, and the credit for the book it is taken from. Each ties to its article; the
  summary lists the one article whose author has no note.

## Reading the summary

- **Text** — counts against the S1 targets (✓ or ≠ target): 1,189 chapters, 31,064 verses,
  2,197 section headings + 59 labels, 4,817 `*` markers, 26 Perspectives boxes set aside.
- **Italic-only lines** — every italic line inside a chapter is claimed (title, verse text or
  label); **unclaimed must be 0**, or the run fails.
- **PDF quirks fixed** — counts of each fix (broken words, fractions, compounds, a table cell
  put back).
- **Checks** — the verse sequence against the public-domain KJV skeleton (with exactly the NLT's
  known omissions and extras), chapters against each book's own navigation list, and hygiene
  (no markup scraps, `*`, double spaces, broken words or fused headings). Verses and headings
  also get the punctuation-spacing checks: no word run into an opening bracket or quote, no
  space after one, no space before closing punctuation, no closing mark run into a word, no
  number spread digit by digit, no mark run into a quoted line break's " / ". The book's own
  forms pass: a spaced ellipsis, an editorial completion inside a word ("x[s]"), "B.C.". Any ✗
  blocks the write.
- **Cross-check** (with `--epub`) — every verse where the PDF parse and the EPUB differ gets one
  class. The two that must be **0**: *fix regressions* (a fix broke a verse the raw parse had
  right) and *open, EPUB text without damage*. Open items in visibly damaged EPUB verses are
  listed for reference.
- **Notes** — the counts against their targets (4,817 textual notes in 1,072 blocks, 2,467 study
  notes); the textual notes by label kind and by anchor (each breakdown sums to the total); every
  `*` matched to a note (*markers without a note* and *notes without a marker* must be **0**); the
  study notes' reference shapes and callouts (*callouts without a note* must be **0**); each
  `ref:` link by how the book's own link target compares (*unexplained* must be **0**); and the
  note checks — hygiene (the punctuation-spacing checks included), Markdown flanking and the
  Markdown-to-text round trip. Any ✗ blocks the write.
- **Notes cross-check** (with `--epub`) — the same classes and evidence rules, note by note. The
  EPUB's markup adds spaces the book doesn't print ("word ." , "2: 5"); both sides close them up
  alike before comparing. A difference that is only in where the spaces fall is judged space by
  space, with the raw parse as the witness: a space the EPUB moved is EPUB damage, a space a fix
  took out that the raw parse and the EPUB both print is a fix regression — even in a note the
  EPUB damaged elsewhere — and a broken word the PDF kept is open. Again *fix regressions* and
  *open, EPUB text without damage* must be **0**.
- **Feature articles** — the callout lines (269: 101 + 94 + 24 for the three article features,
  50 for What the Bible Says About, 3 of them in book introductions; *callouts without an
  article* must be **0**); per feature the articles against their targets (101, 94, 24), their index entries,
  how often each is called out, where the notes attach, the passages' shapes, what the text
  prints (paragraphs, quotations, lists, …) and its length in words; the anchors outside their
  passage and the callout lines inside a verse, listed; the two-book passages and their
  cross-references; links and fixes as for the notes; and the article checks (every callout
  matched, every article indexed and placed, links explained, hygiene and Markdown). Any ✗
  blocks the write.
- **Articles cross-check** (with `--epub`) — the same classes and evidence rules, article by
  article: the printed body against the EPUB's, keyed by feature and printed passage. Again
  *fix regressions* and *open, EPUB text without damage* must be **0**.
- **Topics and Perspectives** — the topics' index, topics, quotations, quoted references and
  subheads, and the boxes and their index, against their targets (50, 502, 503, 240; 26); each
  topic's callouts (*callouts without a topic* must be **0**) and where the notes attach; every
  quotation against EMB's own verse text by class — identical, the same words, a part of the
  verse text, parts joined by an ellipsis or a bracketed word, or other (each *other* must be one
  the converter lists as the book's own edit); the boxes whose index prints another passage, the
  anchors outside a passage, the box inside a verse, and the notes shown before an earlier
  article, all listed; words, links and fixes as above; and the checks (every callout matched,
  every topic and box indexed and placed, index passages and quotations explained, links,
  hygiene and Markdown). Any ✗ blocks the write.
- **Topics and boxes cross-check** (with `--epub`) — the same classes and evidence rules: a topic
  keyed by its number in the book's index (found by its head, or by its first subhead where the
  EPUB lost the head, then marked damaged), a box by the passage it prints. Again *fix
  regressions* and *open, EPUB text without damage* must be **0**.
- **Charts** — the Charts Index's entries and the images they claim (44 each; on the page the
  index links or the next); the passages by shape (range, cross-chapter, verse, whole chapters)
  and where each chart stands (closes its passage, inside it, after it — those listed); the
  images' type and sizes; and every image in the PDF counted by kind (charts, callout icons,
  introduction figures, a page of its own, front matter, the feature region, and *unclassified*,
  which must be **0**). The checks: every entry claims one image, every chart-sized image is
  claimed, every image is named by exactly one note, the index links into the chart's book, no
  chart stands inside a verse, `assets/EMB` holds only this run's images, title hygiene. Any ✗
  blocks the write.
- **Book introductions** — the introductions (66), their section heads by printed form (in one
  order in every introduction), the What's the Point boxes, the timelines and their entries, the
  paragraphs, lists, labels and quotations, what was set aside (callout lines, chapter 1's
  heading), the links by evidence, the words (shortest, median, longest) and the figures (66,
  each claimed by its introduction; type and sizes). The checks: every book has its introduction,
  every figure is claimed once, every link is explained, hygiene and Markdown, and every line is
  placed (the heads in one order, the titles agreeing). Any ✗ blocks the write.
- **Introductions cross-check** (with `--epub`) — keyed by book and section (each head, and the
  What's the Point box): the EPUB's text from the book's first head to its first chapter, cut at
  each section's opening line. A head the EPUB lost merges its section into the one before, both
  marked damaged (listed). The same classes and evidence rules; again *fix regressions* and
  *open, EPUB text without damage* must be **0**. The EPUB's re-encoded figures witness only
  whether a figure stands under its caption.
- **Front matter, reading plan, Personal Gold authors** — the front-matter pieces (5) and what
  each prints by kind (heads, paragraphs, lists and items, roles and names, divisions, groups and
  people) and its words; the contents pages and reference sections set aside; the links by
  evidence; the plan's days (365), readings (1,460) and links (1,465), its readings by shape,
  those that run into the next book, carry a part-verse letter or end on a verse the NLT omits
  (listed), and its link pages by evidence; the author notes (23) and credits (24), how many tie
  to an article, and the article without a note (listed); words and fixes. The checks: five
  pieces, titled; every line placed; links explained; 365 days of 4 readings; every `ref:`
  target a real passage; the plan's link pages explained; notes and credits tied; hygiene and
  Markdown. Any ✗ blocks the write.
- **Documents cross-check** (with `--epub`) — keyed by front-matter piece and section, plan day,
  author note and credit, each found in the EPUB by its opening words and ended at its closing
  words; one found only loosely (words run together, a scrap glued on) is damaged, and one whose
  opening the EPUB lost runs into the part before it (listed). The same classes and evidence
  rules; again *fix regressions* and *open, EPUB text without damage* must be **0**.
- **Charts cross-check** (with `--epub`) — the EPUB's images are re-encoded smaller, so it can't
  witness bytes. Its Charts Index witnesses each title and reference (*agree*, *visible EPUB
  damage*, or *open*, which must be **0**), and its images witness where each chart stands: a
  chart is *at the same place* when an EPUB image of its shape follows the same verse.

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
- `test_licensing_safety.test_clean_checkout_bakes_zero_assets` and
  `test_no_image_is_committed_under_data` — a clean checkout bakes no images, and no image is
  ever committed under `data/` (ADR-0012).
- `test_licensing_safety.test_clean_checkout_bakes_zero_documents` — a clean checkout bakes no
  documents (ADR-0012).

See [../../THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) and
[../../data/SOURCES.md](../../data/SOURCES.md) for the licensing record.
