![Concord — Scripture, served locally.](docs/banner.svg)

# Concord

A self-hosted, LAN-first, read-only Scripture API. It serves multiple public-domain Bible
translations — aligned by book, chapter, and verse — from one canonical SQLite source. It
also does semantic search: ask for verses by idea, not just keyword, and the right passages
come back even when they don't share a word. And it knows where Scripture happened: ask where
a place is, or which places a passage names, and the coordinates come back — honestly marked
when a location is genuinely unknown. Once built, it runs entirely offline: no CDNs, no
telemetry, no phone-home.

### Where to next?

- **A developer who wants to get hands-on?** → [Quick start](#quick-start), including [semantic search](#semantic-search) and the new [geography](#geography) endpoints.
- **Here because Scripture matters to you, and you're curious what this is?** → [What is this, really?](#what-is-this-really)
- **Looking for a polished Bible app to actually use?** → [songbird](https://github.com/kbennett2000/songbird) (desktop) or [soap-journal-mobile](https://github.com/kbennett2000/soap-journal-mobile) (phone).

## What is this, really?

Hi. You found Concord, and you might be wondering what you're looking at.

Concord is a small piece of software that serves Bible verses. It runs on a computer you
(or your church, or your office) controls — not on someone else's cloud. Once it's set up,
it works offline, forever, without phoning home to anyone. It can also find verses by
*meaning* — ask for "verses about anxiety" and it surfaces the passages that fit, even the
ones that never use the word. And it can tell you *where* — where Capernaum is, or which
places Paul passed through in a chapter — and it stays honest when a location is lost to
history rather than guessing at one.

But here's the thing: **Concord isn't an app you use directly.** It's the foundation that
other apps are built on. Think of it like the foundation of a house — essential, but you
don't live in the foundation. You live in the house.

### Are you looking for a Bible app to actually use?

If you want a polished, end-user app that lets you read, journal, take notes, and reflect on
Scripture — try [songbird](https://github.com/kbennett2000/songbird) (desktop) or
[soap-journal-mobile](https://github.com/kbennett2000/soap-journal-mobile) (phone). They're
probably what you actually want.

songbird is built on top of Concord — a polished desktop app that runs against this very
`/v1` surface. soap-journal-mobile is offline-first and goes anywhere, so it runs on its own
and doesn't depend on Concord's LAN server at all.

Concord itself is for the builders.

### "But could I build something with this? I've never coded."

Maybe. Honestly.

The hardest part of building software is usually the data — getting it, cleaning it,
organizing it. Concord hands you 13 English Bible translations plus the original-language
texts — the SBL Greek New Testament and the Hebrew Old Testament — fully aligned, ready to
query, in a single tiny request. The "hard part" is
already done.

What's left is just *asking it questions* and *showing the answers*. Both of those are more
approachable than they sound, and there's a growing universe of tutorials and AI assistants
that can walk you through it patiently.

A tutorial written for someone in exactly your shoes is here:
**[concord-tutorial-web](https://github.com/kbennett2000/concord-tutorial-web)** — a free,
five-lesson course that takes you from "what's an API?" to a real app you built yourself,
running on your own computer. No experience needed. If that "I've never coded" voice is you,
start there — and when you've finished, **[concord-tutorial-react](https://github.com/kbennett2000/concord-tutorial-react)**
picks up right where it leaves off and walks you into React — and
**[concord-tutorial-ai](https://github.com/kbennett2000/concord-tutorial-ai)** finishes the
ladder: the AI everyone is talking about, taught to look Scripture up in *your* Concord instead
of remembering it. Still no experience needed. (The next sections of this README are written for
developers — but the courses were written for you.)

## Quick start

Requirements: Docker, Docker Compose, a LAN.

```bash
git clone https://github.com/kbennett2000/concord
cd concord
docker compose up -d
curl localhost:8000/healthz
```

That last line returns JSON with translation and verse counts. Open `localhost:8000/docs` in
a browser for interactive Swagger documentation — it works fully offline.

Prefer not to build? Pull the prebuilt image instead — see [Deployment](#deployment).

Want a verse?

```bash
curl 'localhost:8000/v1/verses/John%203:16'
```

Or find verses by meaning:

```bash
curl 'localhost:8000/v1/semantic-search?q=do+not+be+anxious'
```

The full API reference is in [`docs/API.md`](docs/API.md). Configuration, deployment, and the
rest are below.

## What's in the box

Twenty-seven endpoints. Each is documented in full — with real request/response examples — in
[`docs/API.md`](docs/API.md).

| Endpoint | What it does |
|---|---|
| `GET /v1/verses/{ref}` | Fetch a verse, range, list, or chapter across one or more translations. |
| `GET /v1/chapters/{book}/{chapter}` | Fetch a whole chapter, multi-translation aware. |
| `GET /v1/search` | Full-text search — one translation, or across several at once with `?translations=`. |
| `GET /v1/semantic-search` | Meaning-based search — find verses by idea, rendered in any translation. |
| `GET /v1/cross-references/{ref}` | Cross-references for a verse, optionally with target text. |
| `GET /v1/places` | Browse places, filtered by type, status, or name. |
| `GET /v1/places/{id}` | One place's detail — coordinates, confidence, and how honestly it's located. |
| `GET /v1/places/{id}/verses` | The verses that mention a place. |
| `GET /v1/verses/{ref}/places` | The places a verse or passage names. |
| `GET /v1/journeys` | Browse the curated biblical journeys (Paul's missionary journeys, the Exodus). |
| `GET /v1/journeys/{id}` | One journey — its ordered stops resolving to real places, plus source and dating. |
| `GET /v1/places/{id}/journeys` | The journeys that pass through a place (the reverse lookup). |
| `GET /v1/translations/{translation}/notes/{book}/{chapter}` | Translator's, study, and text-critical notes for a passage — user-supplied, never shipped in the public image. |
| `GET /v1/notes/search` | Keyword search over translator's notes — user-supplied, never shipped in the public image. |
| `GET /v1/translations/{translation}/headings/{book}/{chapter}` | The section headings that anchor a chapter ("The Creation", "The Beatitudes"), per translation. |
| `GET /v1/topics` | Browse topical-Bible subjects (Nave's), filtered by name or section. |
| `GET /v1/topics/{id}` | One topic's detail — its verse count and any "see also" redirect. |
| `GET /v1/topics/{id}/verses` | The verses curated under a topic, optionally with text. |
| `GET /v1/verses/{ref}/topics` | The topics a verse or passage appears under. |
| `GET /v1/strongs` | Browse the Strong's lexicon, filtered by lemma/transliteration/gloss or language. |
| `GET /v1/strongs/{id}` | One Strong's entry — lemma, transliteration, gloss, and full definition. |
| `GET /v1/strongs/{id}/verses` | The verses where a Strong's number occurs (a concordance), optionally with text. |
| `GET /v1/verses/{ref}/words` | The tagged original-language tokens of a verse — surface, Strong's, morph, gloss. |
| `GET /v1/random` | A random verse, optionally filtered by book or testament. |
| `GET /v1/books` | The 66-book catalog with metadata. |
| `GET /v1/translations` | The loaded translations with metadata. |
| `GET /healthz` | Liveness plus row counts. |

Under the hood, Concord is three packages. `bible-core` is the engine — schema, loader,
reference parser, and queries — with **zero web dependencies**, so a Python app can embed it
in-process and skip HTTP entirely. `bible-semantic` is the embedding engine behind semantic
search — also web-free. `bible-api` is the thin FastAPI layer that wraps them. The `/v1`
prefix is a promise: encode against this surface with confidence.

### Semantic search

`GET /v1/semantic-search` finds verses by meaning. Ask for `verses about anxiety` and you get
the passages that fit — even ones that never use the word — ranked by closeness.

The search runs over one embedded translation, the **World English Bible (WEB)**, in
meaning-space. What it finds are verse *references*, so you can read them in whatever
translation you want: add `?translation=KJV` and the same hits come back as KJV text. It runs
fully offline like everything else — the embedding model is baked into the image, and nothing
is ever sent anywhere.

```bash
curl 'localhost:8000/v1/semantic-search?q=the+good+shepherd&translation=KJV'
```

The full parameters — `limit`, `min_score`, `include_text` — are in [`docs/API.md`](docs/API.md).

### Geography

`GET /v1/places` and its companions answer *where*. Every place has a stable id and is properly
disambiguated — the several Antiochs and Bethlehems are distinct entries, not one fuzzy point —
and the link runs **both ways**: ask a place for its verses, or ask a verse (or a whole chapter)
for the places it names.

```bash
curl 'localhost:8000/v1/verses/Acts+17/places'   # Athens, Berea, Thessalonica, Amphipolis, ...
```

What gives it character is honesty about uncertainty. **Concord never invents a pin.** A place it
can locate is `identified`, with coordinates (Jerusalem, 31.78°N 35.23°E). A place scholars place
differently is `disputed` — a best-guess coordinate, flagged as contested. A place whose location
is genuinely lost is `unknown`, with no coordinates at all rather than a fabricated one: the land
of Nod, east of Eden, comes back honestly marked unknown. (Two more statuses round it out:
`symbolic` for a name used non-literally, `multiple` for something itinerant like the tabernacle.)
Coordinates are always named `latitude`/`longitude` fields — never a bare pair you could read
backwards.

The data is OpenBible.info's, **1,340 places** linked across the canon. The full parameters — the
filters, pagination, and the honest null-coordinate response — are in [`docs/API.md`](docs/API.md).

### Topics

`GET /v1/topics` answers *what about*. Browse curated subjects — "Faith", "Care", "The Creation" —
from **Nave's Topical Bible** (5,319 topics), and the link runs **both ways**: ask a topic for its
verses, or ask a verse for the topics it appears under.

```bash
curl 'localhost:8000/v1/topics?q=anxiety'              # finds ANXIETY (→ see_also: care)
curl 'localhost:8000/v1/verses/Philippians+4:6/topics' # Care, Prayer, Thankfulness, ...
```

Nave's own "See X" cross-references are preserved: a redirect topic carries a `see_also` pointer
and no verses of its own (so `anxiety` points you to `care`, where the verses live). The full
parameters — name/section filters, pagination, and `include_text` — are in
[`docs/API.md`](docs/API.md).

### Word study

`GET /v1/strongs` answers *what does the original word mean*. Browse the **Strong's lexicon** —
the Greek lexicon from [STEPBible](https://github.com/STEPBible/STEPBible-Data) — by lemma,
transliteration, or gloss, and pull one entry's full definition. Ids are forgiving: `g0026`,
`g26`, and `G26` all resolve to the same entry.

```bash
curl 'localhost:8000/v1/strongs?q=love&language=grc'   # ἀγαπάω (G25), ἀγάπη (G26), ...
curl 'localhost:8000/v1/strongs/G26'                   # ἀγάπη — "love", with full definition
```

And the link runs **both ways**, over the **SBL Greek New Testament** and the **Hebrew Old
Testament** (each loaded as a translation — `?translation=SBLGNT` / `?translation=OSHB`): ask a
Strong's number for every verse it appears in, or ask a verse for its tagged original-language words
— each with its lemma, morphology, and gloss. Greek (`G…`) and Hebrew (`H…`) share one lexicon.

```bash
curl 'localhost:8000/v1/strongs/G26/verses'            # every verse with ἀγάπη — a concordance
curl 'localhost:8000/v1/verses/John+3:16/words'        # the tagged Greek tokens of John 3:16
curl 'localhost:8000/v1/strongs/H430/verses'           # every verse with אֱלֹהִים ("God")
curl 'localhost:8000/v1/verses/Genesis+1:1/words'      # the tagged Hebrew tokens of Genesis 1:1
```

The right text is chosen automatically — Hebrew (`OSHB`) for an `H…` id or an OT reference, Greek
(`SBLGNT`) for a `G…` id or an NT reference — and `?text=` overrides it. The Hebrew OT uses
English/NRSV verse numbers (so it lines up with the English Bibles) and is served right-to-left
(`direction: "rtl"` in `/v1/translations`). Aligning each English word to its underlying
Greek/Hebrew token is deliberately out of scope.

### Journeys

`GET /v1/journeys` answers *where did they go*. A curated handful of well-known biblical
itineraries — **Paul's three missionary journeys, his voyage to Rome, and the Exodus** — each an
**ordered sequence of existing places**, so a map client can draw the route as a polyline.

```bash
curl 'localhost:8000/v1/journeys'                 # the curated set
curl 'localhost:8000/v1/journeys/paul-first'      # 15 ordered stops, Antioch → ... → Antioch
curl 'localhost:8000/v1/places/a6c704a/journeys'  # which journeys pass through Pisidian Antioch
```

Journeys **reuse the geography** — every stop is a reference into the same place data (and its
honesty model), never new geography — so a stop the map can't pin (a low-confidence wilderness
station on the Exodus) is surfaced honestly rather than invented. And it stays honest about the
route itself: each journey is **one commonly proposed reconstruction**, carrying its `source` and a
`note` saying so, dated as a whole. Competing routes, route variants, and segment-level dating are
deliberately out of scope. The itineraries follow the biblical narrative; the link runs **both
ways** (`/v1/places/{id}/journeys` is the reverse). Full parameters are in [`docs/API.md`](docs/API.md).

## Configuration

Every setting has a sensible default; none are required. Set them in the host environment or
in a `.env` file (`docker compose` reads both). See [`.env.example`](.env.example).

| Variable | Default | Meaning |
|---|---|---|
| `BIBLE_API_PORT` | `8000` | Host port the API is published on. The container always listens on 8000 internally; this just remaps the host side. |
| `CONCORD_CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins. `*` suits a trusted LAN. |
| `CONCORD_DEFAULT_TRANSLATION` | `KJV` | Translation used when `?translation(s)=` is omitted. Must be one that's loaded, or the API refuses to start. |
| `BIBLE_DB_PATH` | `/app/bible.db` | Path to the database inside the container. |
| `CONCORD_SEMANTIC_SEARCH` | `1` | Whether `/v1/semantic-search` is served. Set it to `0` to disable (skips loading the embedding model). |
| `CONCORD_SEMANTIC_MAX_CONCURRENCY` | `2` | Max simultaneous semantic inferences; excess is shed with `503` + `Retry-After`. `0` disables the cap. Raise on beefier/AVX2 hardware. |
| `CONCORD_SEMANTIC_TIMEOUT_S` | `10` | Per-inference wall-clock deadline (seconds); a query over budget is shed with `503` + `Retry-After`. `0` disables it. |

Changing the port is one line:

```bash
BIBLE_API_PORT=9001 docker compose up -d   # now on localhost:9001
```

## Requirements

Concord runs on modest, owned hardware. There are two tiers, depending on whether semantic
search is on — measured, not guessed:

| | Core API | + Semantic search |
|---|---|---|
| **Query latency** | instant (in-memory SQLite) | ~92 ms on a 2012 no-AVX2 desktop, ~42 ms on a modern machine — interactive |
| **RAM** | ~256 MB | ~662 MB |
| **To deploy** | <100 MB image | ~450 MB compressed to transfer, ~1.4 GB on disk once loaded |
| **CPU** | anything (even a Raspberry Pi) | x86-64 with AVX (2011+) or Apple Silicon; AVX2 is faster but not required |
| **GPU** | none | none |
| **Network** | none at runtime | none at runtime |

Tested on a 2012 Dell Optiplex 9010 — a $50 used desktop: semantic Scripture search in under
a tenth of a second, fully offline. If it runs there, it runs on whatever you've got.

Geography doesn't move these numbers: it's a small set of data tables baked into `bible.db`,
with no model and no new runtime — the place lookups are instant SQLite reads like the rest of
the core API.

## Deployment

The database, the embedding model, and the precomputed verse vectors are all **baked into
the image** at build time — no volumes, no separate data step. A fresh container is
immediately ready and identical to every other container built from the same source.

**The easy path — pull the published image.** A prebuilt image is published to GHCR, so you
can skip the ~20-min build entirely and just pull it (no auth required):

```bash
docker pull ghcr.io/kbennett2000/concord:v1.2.0     # or :latest
docker run -d -p 8000:8000 ghcr.io/kbennett2000/concord:v1.2.0
curl localhost:8000/healthz
```

The image is `linux/amd64` and, like a locally-built one, runs fully offline once pulled. To
use it from compose, point the `image:` at the published tag instead of building locally. The
build-from-source and `docker save`/`scp` paths below remain available — pulling is just the
quickest way in.

Deploy to a LAN host by building from source (replace `192.168.1.62` with yours):

```bash
rsync -a --exclude .git --exclude data/private ./ user@192.168.1.62:~/concord/
ssh user@192.168.1.62 'cd ~/concord && docker compose up -d'
```

Then from any LAN client: `curl http://192.168.1.62:8000/healthz`.

**Build on a capable machine, run on a modest one.** Embedding the corpus happens once at
image-build time and takes ~20–30 minutes — fast on a recent CPU, but slow on an old one
(an AVX2-less box could take an hour or more). So build the image where it's quick, then ship
the built image to the modest box rather than building there:

```bash
docker save concord:latest | gzip > concord.tar.gz          # on the capable machine (~450 MB)
scp concord.tar.gz user@192.168.1.62:~/                      # to the LAN box
ssh user@192.168.1.62 'gunzip -c concord.tar.gz | docker load && docker compose up -d'
```

The modest box only ever runs the fast query-time path. Querying works fully offline —
verified with the network physically off (`docker run --network none …` still serves
`/v1/semantic-search` and `/healthz`).

**Verifying it's truly offline.** The image carries every asset it needs, including the
Swagger UI bundle, so `/docs` renders with no internet at all:

```bash
docker run --rm --network none -p 8000:8000 concord:latest &
sleep 6
curl -s localhost:8000/docs | grep -Eq 'jsdelivr|unpkg|fonts.googleapis' \
  && echo 'FAIL: reaches a CDN' || echo 'OK: /docs is fully self-hosted'
```

The container starts healthy (the built-in healthcheck polls `/healthz`), and
`make docker-verify` runs the health, random-verse, and no-CDN checks against a running
instance.

**Upgrading from an older Concord?** Rebuild the database. The geography tables (v3) are now
part of the required schema, so a `bible.db` built before v3 fails fast at startup with a
rebuild hint — `make build-db`, or just rebuild the image, which bakes a fresh one. A clean
`docker compose up --build` needs no thought here; only a hand-carried older database does.

## Security

Concord is built for a **trusted LAN**: read-only, no authentication, no writes, and no
internet access at runtime. It runs as a non-root user, opens its database read-only, caps
request input sizes, and sets `X-Content-Type-Options: nosniff`. CORS is intentionally open
(`*`) with credentials disabled — correct for an unauthenticated, read-only service on a
trusted network.

The compute-heavy `/v1/semantic-search` is protected by two in-process bounds, each shedding
overload with `503` + `Retry-After`: a concurrency cap on how *many* inferences run at once
(`CONCORD_SEMANTIC_MAX_CONCURRENCY`, default 2) and a wall-clock deadline on how *long* a
single one may run (`CONCORD_SEMANTIC_TIMEOUT_S`, default 10s). The deadline bounds caller
wait, not CPU (a slow inference runs to completion and keeps its slot), so on slow (non-AVX2)
hardware you should **still set a client / reverse-proxy read-timeout** as defense-in-depth
(see [`docs/SECURITY.md`](docs/SECURITY.md)).

**It is not hardened for the public internet.** Before exposing it beyond a LAN, put a
reverse proxy (TLS), authentication, and rate limiting in front of it. The full threat model
and the checklist for public exposure are in [`docs/SECURITY.md`](docs/SECURITY.md).

## The data

Concord bundles **13 public-domain English translations** (KJV, WEB, ASV, YLT, BSB, and others
— see `GET /v1/translations` for the full list), each with its own public-domain notice, plus the
original-language texts — the **SBL Greek New Testament** (`?translation=SBLGNT`) and the **Hebrew
Old Testament** (`?translation=OSHB`, right-to-left). Full provenance is in
[`data/SOURCES.md`](data/SOURCES.md).

Cross-references come from the OpenBible.info dataset (344,799 of them):

> Cross-reference data courtesy of [OpenBible.info](https://www.openbible.info/labs/cross-references/), licensed under a Creative Commons Attribution (CC BY) license.

Place coordinates and the place↔verse links come from OpenBible.info's Bible-Geocoding dataset
(1,340 places):

> Place data courtesy of [OpenBible.info](https://github.com/openbibleinfo/Bible-Geocoding-Data), licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license.

Topical browsing comes from Nave's Topical Bible (Orville J. Nave, 1897 — public domain),
via a machine-readable compilation (5,319 topics):

> Topical data from Nave's Topical Bible (public domain; 1897), via [BradyStephenson/bible-data](https://github.com/BradyStephenson/bible-data), licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license.

The original-language texts and the Strong's lexicons come from STEPBible — the Greek NT (`SBLGNT`,
7,917 verses, the SBL-edition word selection) from the Amalgamated Greek NT, and the Hebrew OT
(`OSHB`, 23,145 verses) from the Amalgamated Hebrew OT (Westminster Leningrad Codex tradition,
loaded under English/NRSV verse numbers, right-to-left):

> Original-language and lexicon data created by [STEPBible.org](https://github.com/STEPBible/STEPBible-Data) based on work at Tyndale House Cambridge, licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license; the SBLGNT is © 2010 Society of Biblical Literature & Logos Bible Software, CC BY 4.0.

Some translations aren't public-domain and can't be redistributed. Concord supports them
through a gitignored `data/private/` directory: drop a non-distributable translation's JSON
there and the loader picks it up automatically on a local build, while it never enters the
public repo or a shared image. The pattern lets an operator run translations they're licensed
for without ever committing them.

Semantic search uses IBM's
[`granite-embedding-311m-multilingual-r2`](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2)
embedding model — **Apache 2.0 licensed**, pinned to a fixed revision and baked into the
image (the int8 build, ~313 MB). It's downloaded once at build time and never contacted at
runtime.

## What Concord doesn't do (yet)

Concord is deliberately scoped. Semantic search landed in v2, geography in v3, and a curated
journeys layer in v7; a few things still haven't made a release, on purpose:

- **Competing routes for the journeys.** The curated journeys (Paul's missionary journeys, the
  Exodus) shipped in v7 as **one commonly proposed reconstruction each** — ordered sequences of
  existing places, reusing v3's geography rather than rebuilding it. What's deliberately *not*
  modeled is the **competing routes** scholars propose, route variants, and segment-level dating —
  a distinct research problem, deferred to its own future layer.
- **Catholic and deuterocanonical books.** The schema is ready for them, but the data, naming
  conventions, and Vulgate psalm-numbering mapping are all distinct work that didn't belong in
  a clean release. Future work.
- **Notes semantic search.** Keyword search over translator's notes shipped in v5
  (`GET /v1/notes/search`); *meaning-based* search over them is designed but gated behind real
  demand — the note-embedding corpus is large and tied to restrictively-licensed source text, so
  it's opt-in/local rather than something every instance pays for. Keyword notes search covers the
  common case.
- **Multi-translation *semantic* search.** Not a gap — it's deliberately not a thing. Semantic
  search is already translation-agnostic: it ranks verse *references* in one meaning-space (WEB) and
  renders them in whatever translation you ask for, so "search all translations" has no meaning for
  it. (Keyword multi-translation search *did* ship in v5 — see `GET /v1/search?translations=`.)
- **Ship translator's notes.** The notes endpoint
  (`GET /v1/translations/{translation}/notes/{book}/{chapter}`) is fully wired and live, but
  the public image ships **zero** notes — the richest source (NET) is copyrighted, and notes
  are user-supplied by design. So on a stock image this endpoint returns `200` with an empty
  list for every translation. To populate it, bake your own legally-obtained notes in via the
  gitignored `data/private/notes/` directory — see
  [`docs/API.md`](docs/API.md#get-v1translationstranslationnotesbookchapter) and
  [`examples/notes-sample.json`](examples/notes-sample.json) for the file shape.

If any of these would unblock a project of yours, open an issue and say so — it shapes what
gets built next.

## Building on Concord

Concord exists to be built on — and a small but growing ecosystem already runs on it:

- **The app it's for:** [songbird](https://github.com/kbennett2000/songbird) is a polished
  end-user Bible app built on top of Concord — a working desktop client of this `/v1` surface.
- **Embedding in-process:** because `bible-core` has no web dependencies, a Python project can
  import it directly and query Scripture without running the HTTP server at all.
  [`examples/embed_in_process.py`](examples/embed_in_process.py) is a runnable example — it
  parses a reference and fetches a verse with no server running, then (if the embedding model
  and vector store are present) does a `bible-semantic` query in-process too.
- **Learn to build on it — three courses, from "what's an API?" to reading a real AI codebase:**
  **[concord-tutorial-web](https://github.com/kbennett2000/concord-tutorial-web)** builds your
  first real app in plain HTML and JavaScript (no experience needed), and
  **[concord-tutorial-react](https://github.com/kbennett2000/concord-tutorial-react)** picks up
  from there into React — ending with you reading songbird's own source and finding you can…and
  **[concord-tutorial-ai](https://github.com/kbennett2000/concord-tutorial-ai)** adds local AI
  tool-calling in plain JavaScript — ending with the student reading concord-mcp's source at
  v1.0.0 and recognizing every part.

The `/v1` prefix means today's responses are a contract. Build against them with confidence.

## License & attribution

- **Code:** MIT © 2026 Kris Bennett — see [`LICENSE`](LICENSE).
- **Bundled translations:** the 13 English translations are public domain — see
  [`data/SOURCES.md`](data/SOURCES.md).
- **Original-language texts (SBLGNT, OSHB):** [STEPBible-Data](https://github.com/STEPBible/STEPBible-Data)
  (Tyndale House Cambridge), licensed under Creative Commons Attribution 4.0 International
  (CC BY 4.0); the SBLGNT is © 2010 Society of Biblical Literature & Logos Bible Software; the
  Hebrew descends from the OpenScriptures / Westminster Leningrad Codex text.
- **Strong's lexicons (Greek + Hebrew):** [STEPBible-Data](https://github.com/STEPBible/STEPBible-Data)
  (Tyndale House Cambridge; the Brief lexicons draw on Abbott-Smith for Greek and BDB for Hebrew),
  licensed under Creative Commons Attribution 4.0 International (CC BY 4.0). The Strong's numbering
  (1890) is public domain.
- **Cross-references:** [OpenBible.info](https://www.openbible.info/labs/cross-references/),
  licensed under Creative Commons Attribution (CC BY).
- **Place data:** [OpenBible.info Bible-Geocoding-Data](https://github.com/openbibleinfo/Bible-Geocoding-Data),
  licensed under Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Topical data:** Nave's Topical Bible (public domain; 1897), via
  [BradyStephenson/bible-data](https://github.com/BradyStephenson/bible-data),
  licensed under Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Embedding model:** [`ibm-granite/granite-embedding-311m-multilingual-r2`](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2),
  Apache 2.0 © IBM.
