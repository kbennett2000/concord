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
- **Looking for a polished Bible app to actually use?** → [soap-journal](https://github.com/kbennett2000/soap-journal) (desktop) or [soap-journal-mobile](https://github.com/kbennett2000/soap-journal-mobile) (phone).

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
Scripture — try [soap-journal](https://github.com/kbennett2000/soap-journal) (desktop) or
[soap-journal-mobile](https://github.com/kbennett2000/soap-journal-mobile) (phone). Both are
built *on top of* Concord, and they're probably what you actually want.

Concord itself is for the builders.

### "But could I build something with this? I've never coded."

Maybe. Honestly.

The hardest part of building software is usually the data — getting it, cleaning it,
organizing it. Concord hands you 13 Bible translations, fully aligned, ready to query, in a
single tiny request. The "hard part" is already done.

What's left is just *asking it questions* and *showing the answers*. Both of those are more
approachable than they sound, and there's a growing universe of tutorials and AI assistants
that can walk you through it patiently.

A tutorial repo or two — written for someone in exactly your shoes — is on the way. When it
lands it'll live alongside this one, at `kbennett2000/concord-tutorial-*`. In the meantime,
keep reading if you're curious. The next sections are written for developers, but you might
surprise yourself.

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

Thirteen endpoints. Each is documented in full — with real request/response examples — in
[`docs/API.md`](docs/API.md).

| Endpoint | What it does |
|---|---|
| `GET /v1/verses/{ref}` | Fetch a verse, range, list, or chapter across one or more translations. |
| `GET /v1/chapters/{book}/{chapter}` | Fetch a whole chapter, multi-translation aware. |
| `GET /v1/search` | Full-text search within a single translation. |
| `GET /v1/semantic-search` | Meaning-based search — find verses by idea, rendered in any translation. |
| `GET /v1/cross-references/{ref}` | Cross-references for a verse, optionally with target text. |
| `GET /v1/places` | Browse places, filtered by type, status, or name. |
| `GET /v1/places/{id}` | One place's detail — coordinates, confidence, and how honestly it's located. |
| `GET /v1/places/{id}/verses` | The verses that mention a place. |
| `GET /v1/verses/{ref}/places` | The places a verse or passage names. |
| `GET /v1/random` | A random verse, optionally filtered by book or testament. |
| `GET /v1/books` | The 66-book catalog with metadata. |
| `GET /v1/translations` | The loaded translations with metadata. |
| `GET /healthz` | Liveness plus row counts. |

Under the hood, Concord is two packages. `bible-core` is the engine — schema, loader,
reference parser, and queries — with **zero web dependencies**, so a Python app can embed it
in-process and skip HTTP entirely. `bible-api` is the thin FastAPI layer that wraps it. The
`/v1` prefix is a promise: encode against this surface with confidence. (Semantic search adds
a third package, `bible-semantic` — the embedding engine, also web-free.)

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

Deploy to a LAN host (replace `192.168.1.62` with yours):

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

## The data

Concord bundles **13 public-domain translations** (KJV, WEB, ASV, YLT, BSB, and others — see
`GET /v1/translations` for the full list). Each carries its own public-domain notice; full
provenance is in [`data/SOURCES.md`](data/SOURCES.md).

Cross-references come from the OpenBible.info dataset (344,799 of them):

> Cross-reference data courtesy of [OpenBible.info](https://www.openbible.info/labs/cross-references/), licensed under a Creative Commons Attribution (CC BY) license.

Place coordinates and the place↔verse links come from OpenBible.info's Bible-Geocoding dataset
(1,340 places):

> Place data courtesy of [OpenBible.info](https://github.com/openbibleinfo/Bible-Geocoding-Data), licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license.

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

Concord is deliberately scoped. Semantic search landed in v2 and geography in v3; a few things
still haven't made a release, on purpose:

- **Journeys and routes.** The named next frontier — ordered sequences like Paul's missionary
  journeys or the Exodus, with the competing routes scholars propose for each. It's a distinct
  data-and-modeling problem, and it *builds on* v3's geography (the stable place ids and
  disambiguation exist precisely so a journeys layer can reference this place data rather than
  rebuild it). A future version.
- **Catholic and deuterocanonical books.** The schema is ready for them, but the data, naming
  conventions, and Vulgate psalm-numbering mapping are all distinct work that didn't belong in
  a clean release. Future work.
- **Multi-translation search.** Search hits a single translation at a time. Cross-translation
  search introduces noise (near-duplicate hits) that's worth solving carefully when the time
  comes.

If any of these would unblock a project of yours, open an issue and say so — it shapes what
gets built next.

## Building on Concord

Concord exists to be built on.

- **Existing apps:** [soap-journal](https://github.com/kbennett2000/soap-journal) and
  [soap-journal-mobile](https://github.com/kbennett2000/soap-journal-mobile) are end-user
  Bible apps that consume this surface.
- **Embedding in-process:** because `bible-core` has no web dependencies, a Python project can
  import it directly and query Scripture without running the HTTP server at all.
- **Coming:** beginner-friendly tutorial repos at `kbennett2000/concord-tutorial-*` — forward
  signal, no timeline yet.

The `/v1` prefix means today's responses are a contract. Build against them with confidence.

## License & attribution

- **Code:** MIT © 2026 Kris Bennett — see [`LICENSE`](LICENSE).
- **Bundled translations:** public domain — see [`data/SOURCES.md`](data/SOURCES.md).
- **Cross-references:** [OpenBible.info](https://www.openbible.info/labs/cross-references/),
  licensed under Creative Commons Attribution (CC BY).
- **Place data:** [OpenBible.info Bible-Geocoding-Data](https://github.com/openbibleinfo/Bible-Geocoding-Data),
  licensed under Creative Commons Attribution 4.0 International (CC BY 4.0).
- **Embedding model:** [`ibm-granite/granite-embedding-311m-multilingual-r2`](https://huggingface.co/ibm-granite/granite-embedding-311m-multilingual-r2),
  Apache 2.0 © IBM.
