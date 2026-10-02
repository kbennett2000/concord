# Private topics — ingest & user flow (Concord v8)

Concord's topical Bible (`/v1/topics*`, ADR-0006) ships with one source, Nave's Topical Bible.
A study Bible may print a topical index of its own — the Every Man's Bible prints the Tyndale
Verse Finder: a topic, then the references it gives. Concord serves such an index **beside**
Nave's, as a second topical source ([ADR-0013](../adr/ADR-0013-private-topics-and-sources.md)):
the same endpoints, every topic carrying its `source`, and `?source=` to page one source.

Like the notes and documents it sits beside, a study Bible's topical index is **copyrighted and
not redistributable**. So Concord ships the *capability*, never the *data*: you supply topics
from a book you own, and they are baked into your **local** `bible.db`. The published image ships
Nave's only.

> **Only load data you have the legal right to use.** Topics you place under `data/private/` are
> never committed and never baked into the published image — that is your responsibility to keep
> clean, and Concord's pipeline is built to make it automatic.

## The user flow

1. **Own the source.** For the Every Man's Bible, its converter writes the Verse Finder for you
   ([emb-ingest](emb-ingest.md)). For anything else, produce JSON matching the contract below by
   whatever means you legally can.
2. **Drop** the JSON at `data/private/topics/<name>.json`, one file per source. The folder sits
   under the already gitignored and dockerignored `data/private/`, so nothing you put there can
   leak.
3. **Rebuild** Concord (`make build-db`, or `make docker-build-private` for your own image). The
   loader reads `data/topics/` (the committed Nave's) and then `data/private/topics/`, validates
   every file and bakes them into your local `bible.db`. The build summary counts all sources
   together:

   ```
   Built bible.db: 20 translations, …, 5502 topics, 141295 topic-verse links, … in 61.0s.
   ```

4. **Served.** `GET /v1/topics` lists every source's topics and appends `sources` — each source
   with its count — so a client can offer a filter; `?source=<name>` pages one source;
   `/v1/topics/{id}`, `/v1/topics/{id}/verses` and `/v1/verses/{ref}/topics` carry each topic's
   `source` ([API](../API.md#get-v1topics)).

A build with no `data/private/topics/` (the public image, CI, any fresh clone) bakes Nave's only,
which is a normal state, not an error.

## The topics JSON contract

One file per source. The loader (`bible_core.topics`) reads every `*.json` directly under
`data/topics/` and then under `data/private/topics/`, each folder's files in sorted order.

```jsonc
{
  "source": "Made-up Topical Index",  // REQUIRED — the source's display name, as clients show and
                                      //   filter it; one file per source
  "topics": [                         // REQUIRED — at least one
    {
      "id": "mti-1",                  // REQUIRED — lower-case letters, digits and "-"; unique
                                      //   across every source. Give a private source a prefix of
                                      //   its own (the Verse Finder uses "vf-") so it never
                                      //   meets a committed id
      "name": "A Made-up Topic",      // REQUIRED — the topic's name as printed
      "section": "A",                 // REQUIRED — one letter A–Z (the index letter)
      "see_also": null,               // a "See X" redirect's target id, else null; a redirect
                                      //   carries no verses (clients follow it)
      "verses": [                     // canonical verse links; a range is listed verse by verse
        {"book": "GEN", "chapter": 1, "verse": 1}
      ]
    }
  ]
}
```

- **Verses** are canonical coordinates, not a translation's text: list each verse a reference
  covers (a range verse by verse, a whole chapter every verse). `book` is a code or any alias;
  a link whose book doesn't resolve is skipped and counted. A verse listed twice under one topic
  is kept once.
- **`see_also` is a redirect** — clients show "See X" and the target's verses, not the topic's
  own. Don't use it for a "see also" between topics that both carry verses.
- **Order:** topics list in one A–Z order across every source, by name ignoring case, then id;
  a topic's verses in canonical order.
- Unknown keys are ignored.

The build **fails loudly**, naming the file, on: invalid JSON; a missing or malformed field; an
empty `topics` list; an id outside the form above; a section that isn't one capital letter; a
source name another file already uses; an id another topic already uses (naming the file that
claimed it first).

The load is **idempotent**: the same inputs produce a byte-identical `bible.db`.

## Why this is safe

The licensing safety is the **dual-ignore rule** (`docs/v4/SPEC.md` §2): `data/private/` is
excluded by **both** `.gitignore` and `.dockerignore`, and `data/private/topics/` sits under it, so
it needs no new ignore entry. Tests enforce the rest:

- `test_licensing_safety.test_private_data_dir_is_ignored` — `data/private/` stays in both ignore
  files.
- `test_licensing_safety.test_clean_checkout_bakes_zero_private_topics` — a build from a checkout
  with no `data/private/` bakes the committed topics only; the same build with a private topics
  file bakes it too, so the zero isn't vacuous.
- `test_licensing_safety.test_public_topics_dir_is_not_ignored` — the mirror guard: the committed
  `data/topics/` must ship.
- `test_topics_loader.test_committed_topics_keep_the_shared_rules` — no committed id carries the
  Verse Finder's `vf-` prefix, so a private build can never collide with one.

See [../../THIRD_PARTY_NOTICES](../../THIRD_PARTY_NOTICES) and
[../../data/SOURCES.md](../../data/SOURCES.md) for the licensing record.
