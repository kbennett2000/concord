# Concord v2 — Semantic Search Build Spec

**Concord v2** adds **semantic search**: ask *"find verses about anxiety"* and get
back the most meaning-relevant passages, with zero keyword overlap required, running
fully offline like everything else in Concord. It is the highest-leverage addition on
the roadmap — it unblocks semantic search itself, a future auto-topical concordance, and
materially better grounded-RAG for any downstream study assistant.

This spec sits alongside the v1 spec (`docs/SPEC.md`), which remains the canon for the
read API. v2 is **purely additive**: `bible-core` is untouched, `bible-api` gains one new
endpoint plus a dependency on a new package, and no existing endpoint changes. The `/v1`
URL prefix stays — semantic search is a new endpoint, not a breaking change, so "v2" is
the milestone, not a URL namespace.

---

## 1. Goals & shape

The capability is **meaning-based retrieval over Scripture**. A natural-language query is
embedded with a small local model, compared against pre-computed verse embeddings by
cosine similarity, and the top matches are returned ranked by score.

v2 is **read-only** and **single-endpoint**: one `/v1/semantic-search` route. Everything
heavy (embedding the whole corpus) happens once at build time and is baked into the image;
the only runtime work is embedding the user's short query and a fast vector scan. It runs
100% offline at runtime, consistent with v1.

A deliberately small footprint is a first-class goal — Concord's promise is "runs on a
modest LAN box," and v2 must keep it. That goal drives the model choice, the ONNX runtime,
and the embed-one-translation decision below.

---

## 2. Architecture — the third package

v2 extends the layering philosophy rather than compromising it. v1 established
`bible-core` (pure) → `bible-api` (web). v2 inserts a middle layer:

```
bible-core      (pure: stdlib sqlite3 only — NO web, NO ML)
     ▲
bible-semantic  (ML: onnxruntime + tokenizers + numpy — NO web)   ← NEW
     ▲
bible-api       (web: FastAPI — depends on both)
```

```
concord/                        # repo root (unchanged from v1)
├── bible-core/                 # UNTOUCHED by v2
├── bible-api/                  # gains one router + a dep on bible-semantic
├── bible-semantic/             # NEW package — ML, web-free
│   ├── pyproject.toml          # deps: onnxruntime, tokenizers, numpy; path dep on ../bible-core
│   ├── src/bible_semantic/
│   │   ├── model.py            # ONNX model load + query-embedding (tokenize→infer→pool→normalize)
│   │   ├── store.py            # read embeddings.db → in-memory numpy matrix; metadata guard
│   │   ├── search.py           # cosine top-k over the matrix (pure, testable)
│   │   └── build.py            # build-time: embed the corpus → embeddings.db
│   └── tests/
├── data/                       # unchanged
├── models/                     # NEW: baked ONNX model weights (gitignored — build artifact)
├── docs/
│   ├── SPEC.md                 # v1 canon
│   └── v2/SPEC.md              # this document
└── scripts/
    └── build_embeddings.py     # thin CLI wrapper over bible_semantic.build
```

**`bible-semantic` is web-free, exactly like `bible-core`.** It may carry ML dependencies
(`onnxruntime`, `tokenizers`, `numpy`) but never a web framework. This preserves the
property that `soap-journal` could, *if it ever wanted in-process semantic search*, depend
on `bible-semantic` and accept the ML weight — while the lightweight offline app can keep
depending on `bible-core` alone. The layers stay clean.

**Two hard invariants now:**
- `bible-core` imports **no web framework and no heavy ML** — it stays tiny (stdlib
  `sqlite3` only), so anything can embed it cheaply.
- `bible-semantic` imports **no web framework** — it's an embeddable ML library, not a
  service. The only web layer remains `bible-api`.

`bible-semantic` reads verse text through `bible-core`'s existing query API (to embed at
build time and to hydrate results); it does not re-implement data access and does not
modify `bible-core`.

---

## 3. Decisions & non-goals

**Model: `ibm-granite/granite-embedding-311m-multilingual-r2`.** Apache 2.0 (clean,
matches the MIT/own-it-forever ethos — no flow-down obligations, no use-restriction policy
to propagate, no vendor kill-switch). 311M params, ModernBERT-based, 768-dim output,
200+ languages with 52 enhanced (including Greek `el` and Hebrew `he`), 32K context,
official ONNX + OpenVINO weights, drop-in with no instruction prefix. Chosen over
EmbeddingGemma-300M (best-in-class but Gemma's custom license) and Qwen3-Embedding-0.6B
(Apache but larger at 600M). See §5.

**Multilingual, decided up front.** The corpus is English-only today, but re-embedding
under a different model later touches everything (the baked vector artifact, the stored
dimension, the runtime model). The multilingual model is chosen now so the day a Spanish,
Latin, Koine Greek, or Hebrew translation is added, semantic search works across it — and
across languages — with no re-embed. The marginal English-only quality given up for that
headroom is a deliberate, accepted trade.

**Embed one translation (WEB), return verse positions, hydrate any translation.** Semantic
meaning is largely translation-independent, so v2 embeds a single modern translation — the
**World English Bible (WEB)**, which is in the corpus, modern (KJV-era English embeds
worse), and public domain. Search happens in WEB-embedding space; the matched **references**
can be rendered in *any* requested translation by joining back through `bible-core`. So a
user can search semantically and read the hits in their preferred translation (see §7).
Embedding all 17 translations is a non-goal for v2 (more storage, and near-duplicate
cross-translation hits add noise).

**Full 768 dimensions.** At ~31,100 verses the entire vector index is ~95 MB at 768-dim
float32 and a query scan is single-digit milliseconds — so there's no reason to spend the
0.5-point quality loss that Matryoshka truncation to 256-dim would buy. Use the model's
native 768-dim output. Matryoshka truncation is noted as a future lever (§5) if the index
ever grows (e.g. embedding multiple translations).

**Vector store: numpy brute-force, persisted in SQLite, baked into the image.** At this
scale an exact brute-force cosine scan is sub-10 ms and needs no ANN index. Vectors are
persisted in a small `embeddings.db` (SQLite, owned by `bible-semantic`, kept separate
from `bible.db` so v1's core is untouched) and loaded into an in-memory numpy matrix at
startup. This keeps the "boring and bulletproof" character: no platform-specific compiled
vector extension to bake and load, just `numpy`. `sqlite-vec` is the alternative only if
the corpus ever reaches millions of vectors — which single-translation Bible search will
not.

**ONNX Runtime + int8, no PyTorch.** Both build-time and query-time inference use
`onnxruntime` (CPU) with the model's tokenizer via the `tokenizers` library — no `torch`,
no `sentence-transformers`, no `transformers`. This is what keeps the image small
(~hundreds of MB, not ~2 GB) and gives graceful CPU-feature fallback on the AVX2-less
target box (§4). An int8-quantized ONNX model is preferred for size and speed.

**Build-time embedding, baked artifact.** Embedding the whole corpus is a one-time batch
job run at Docker build (build has internet to fetch the model); the resulting
`embeddings.db` and the model weights are baked into the image. The runtime never embeds
the corpus and never needs the internet. The model weights *are* needed at runtime (to
embed the query), so they ship in the image.

**Out of scope for v2** (no build without an explicit scope decision):
- Embedding more than one translation.
- Hybrid search (blending keyword FTS5 + semantic) and cross-encoder re-ranking — possible
  future enhancements; v2 is pure dense retrieval.
- Fine-tuning the model on biblical text — use it off-the-shelf.
- The downstream *applications* of this endpoint (auto-topical concordance, RAG study
  assistant) — those consume `/v1/semantic-search`; they are not part of Concord's API.
- Biblical geography — that's the v3 candidate.
- Catholic / deuterocanonical data — still deferred from v1.

---

## 4. Hardware & runtime

Concord's audience runs modest hardware; v2 must stay reachable for them. The reference
target is the project's own LAN box: a 2012 Dell Optiplex 9010 (i5-3540, Ivy Bridge) — a
$50 used desktop. The one wrinkle is that Ivy Bridge has AVX but **not AVX2** (AVX2 arrived
with Haswell, 2013). That matters in exactly one place:

- **Query-time inference** (embedding the user's short query) is a single forward pass —
  trivial compute, comfortably sub-second on that CPU, interactive. AVX2's absence is
  irrelevant here.
- **Build-time corpus embedding** (~31,100 verses, once) is slower without AVX2 — on the
  order of 10–20 minutes on the Optiplex. It's a one-time batch job, not a request path,
  and it has a clean escape hatch: **build on a capable machine** (e.g. G434, which has
  AVX2), bake the artifact into the image, and ship the image to the Optiplex. The Optiplex
  only ever does the fast query-time work. This is the same "build where it's capable, run
  where it's modest" split as the offline-DB story in v1.

ONNX Runtime detects CPU features and falls back to the AVX path automatically when AVX2 is
absent, so the same image runs correctly on the old box without special handling.

Two-tier requirements for the README (design targets; exact figures confirmed at build, in
the v1 "tested on real hardware" spirit):

| | Core API (v1) | + Semantic search (v2) |
|---|---|---|
| **CPU** | Anything — even a Pi | x86-64 with AVX (2011+) or Apple Silicon; AVX2 (2013+) faster, **not** required |
| **RAM** | ~256 MB | ~1.5–2 GB free for the service |
| **Disk** | <100 MB | +~500 MB (model + ONNX runtime + ~95 MB vectors), well under 1 GB |
| **GPU** | None | None |
| **Network** | None at runtime | None at runtime |
| **Model** | — | `granite-embedding-311m-multilingual-r2` (Apache 2.0) |

Lean into the $50-machine fact as a trust signal in the docs: *"Developed and tested on a
2012 Dell Optiplex 9010 — a $50 used desktop. If it runs there, it runs on whatever you've
got."*

---

## 5. The embedding model

`ibm-granite/granite-embedding-311m-multilingual-r2` (IBM, Apache 2.0, May 2026).

| Property | Value |
|---|---|
| License | **Apache 2.0** (clean redistribution; baking into the image is a one-line notice) |
| Params | 311M (ModernBERT, 22-layer encoder) |
| Output dim | 768, with Matryoshka truncation to 512 / 384 / 256 / 128 available |
| Languages | 200+ pretrained; 52 enhanced, incl. Greek (`el`) and Hebrew (`he`) |
| Context | 32K tokens (vastly more than a verse needs) |
| Retrieval quality | MTEB Multilingual Retrieval 65.2 (#2 among open models <500M) |
| Inference | Official ONNX + OpenVINO weights; drop-in, **no instruction prefix** |
| Tokenizer | Gemma-3 tokenizer vocabulary (262K) — vocab only; the package is Apache 2.0 |

**Inference recipe** (the load-bearing detail for the first slice): tokenize with the
model's tokenizer → run the ONNX model → **CLS-pool** (take the first/`[CLS]` token's
hidden state) → **L2-normalize** to a unit vector. There is **no dense projection layer**.
Because vectors are L2-normalized, **cosine similarity is just a dot product** — which is
what makes the query-time scan a single fast matrix-vector multiply.

> *Recipe corrected in Slice S0.* This section originally specified mean-pooling; S0
> verified against the model card that `granite-embedding-311m-multilingual-r2` uses **CLS
> pooling** (model output `[:, 0]`) with no dense layer — surfacing the wrong recipe before
> any corpus was embedded is exactly what S0 exists to do.

**Matryoshka (future lever, not used in v2):** truncating 768→256 drops MTEB Multilingual
Retrieval by ~0.5 points (and 128-dim retains >97%). If the index ever needs to shrink
(e.g. embedding several translations), truncation is the cheap knob. v2 keeps full 768.

**Latin / Koine honesty:** modern Greek and Hebrew are in the enhanced-52 set, so future
Greek/Hebrew texts get tuned retrieval (modern ≠ Koine exactly, but same script and much
shared vocabulary — far better than nothing). Latin is in the 200+ pretrained set but
*not* enhanced, so a Vulgate would get general-purpose embeddings. Acceptable; noted.

---

## 6. Data model — the embeddings store

A new SQLite database, `embeddings.db`, owned by `bible-semantic`, kept separate from
`bible.db` so v1's core is untouched. Like `bible.db`, it is a **build artifact baked into
the image, never committed**.

**`verse_embeddings`**
| column | type | notes |
|---|---|---|
| `book_id` | TEXT | USFM code, matches `bible-core` |
| `chapter` | INTEGER | |
| `verse` | INTEGER | |
| `vector` | BLOB | raw float32 bytes, 768 × 4 = 3072 bytes/verse |

Primary key `(book_id, chapter, verse)`. One row per WEB verse (~31,100 rows, ~95 MB).

**`embedding_meta`** (single row — a guard against silent mismatch)
| column | type | notes |
|---|---|---|
| `model` | TEXT | `ibm-granite/granite-embedding-311m-multilingual-r2` |
| `model_revision` | TEXT | pinned Hugging Face commit SHA the vectors were built with (added in S1) |
| `dim` | INTEGER | 768 |
| `precision` | TEXT | inference precision the corpus was built at — `int8` (the standard) or `fp32` (added in S3a). Query + corpus must match; the guard refuses a mismatch |
| `translation` | TEXT | `WEB` |
| `normalized` | INTEGER | 1 (vectors are unit-normalized) |
| `built_at` | TEXT | ISO timestamp |

At startup, `store.py` reads all rows into a contiguous `numpy` float32 matrix `(N, 768)`
plus a parallel list of `(book_id, chapter, verse)` refs, and **asserts the running query
model (id + revision), dim, and precision match `embedding_meta`** — refusing to serve
mismatched vectors rather than returning garbage similarities.

---

## 7. Endpoint

`GET /v1/semantic-search`

| param | default | notes |
|---|---|---|
| `q` | *(required)* | natural-language query, e.g. `verses about anxiety` |
| `limit` | 20 (max 100) | top-k results |
| `translation` | `WEB` | which translation's **text** to return; search always runs in WEB space |
| `min_score` | *(none)* | optional cosine-similarity floor to drop weak matches |
| `include_text` | `true` | hydrate verse text (mirrors `/v1/cross-references`) |

**Search-in-WEB, display-in-any-translation.** Similarity is computed over WEB embeddings.
The matched references are then hydrated in the requested `translation` by joining through
`bible-core`'s existing `get_verses` — so a user can search semantically and read the hits
in KJV, YLT, or whatever they prefer. `translation=WEB` (default) returns the embedded
text directly.

**Response:**
```json
{
  "query": "verses about anxiety",
  "translation": "WEB",
  "count": 3,
  "results": [
    { "book": "PHP", "chapter": 4, "verse": 6, "reference": "Philippians 4:6", "score": 0.71, "text": "In nothing be anxious..." },
    { "book": "1PE", "chapter": 5, "verse": 7, "reference": "1 Peter 5:7", "score": 0.66, "text": "casting all your worries on him..." }
  ]
}
```

**Errors** reuse the v1 envelope: `q` missing/empty → `422`; unknown `translation` →
`404 unknown_translation` (consistent with how `/v1/search` and `/v1/verses` actually treat
an unknown translation — corrected from `400` in Slice S2b, which reuses v1's
`UnknownTranslationError` path). Empty result set → `200` with `count: 0`.

**Caching.** For a fixed model + vectors, the response to a given query+params is
deterministic and immutable until a rebuild (which is a new image). Mirror `/v1/search`:
body-hash `ETag` + `Cache-Control`, honoring conditional requests.

---

## 8. Build-time embedding generation

`bible_semantic.build` (wrapped by `scripts/build_embeddings.py`) is a reproducible,
idempotent CLI that:

1. Reads every WEB verse from `bible.db` via `bible-core`.
2. For each verse: tokenize → ONNX inference → CLS-pool → L2-normalize → float32 vector.
3. Writes `verse_embeddings` and the `embedding_meta` row into a freshly-built
   `embeddings.db`.

It rebuilds from scratch each run and fails loudly on a missing model or empty corpus. It
runs at Docker build time; the model is downloaded from Hugging Face during build (internet
OK at build) into `models/`, used to generate `embeddings.db`, and both the model weights
and `embeddings.db` are baked into the runtime image. **Build on a capable machine** (§4)
and ship the image; the slow path never runs on the modest box.

---

## 9. Inputs needed

1. **Embed target = WEB** — confirmed present in the corpus; the spec assumes WEB unless
   you'd rather embed a different modern PD translation you hold.
2. **Quantization level** — int8 ONNX is the lean default; fp16 is the higher-fidelity,
   larger alternative. A build-time call; the exact image-size delta gets measured and
   recorded in dev-notes during the deploy slice.

Neither blocks starting the build.

---

## 10. Build plan — sliced for Claude Code

Smallest reviewable, load-bearing units, PR-per-slice, same discipline as v1. The one
intentionally-combined slice is flagged with its reasoning.

| # | Slice | Package(s) | Delivers | Depends on | Review focus |
|---|---|---|---|---|---|
| S0 | Semantic package & inference core | semantic | New `bible-semantic` package (deps: onnxruntime, tokenizers, numpy; web-free); `model.py` query-embedding (tokenize→infer→pool→normalize); model fetch at build/test; a test embedding a known string asserting shape + unit norm. **Updates CLAUDE.md**: add the `bible-semantic` package + its web-free invariant; move semantic search out of the v1 out-of-scope list. | v1 shipped | ONNX pipeline correctness; the web-free boundary on the new package |
| S1 | Embeddings store & corpus build | semantic | `embeddings.db` schema (`verse_embeddings` + `embedding_meta`); `build.py` reads WEB via `bible-core`, embeds all verses, writes the DB; idempotent. Tests: row count = WEB verse count, metadata correct, a known verse vector present + normalized. | S0 | Build correctness; idempotency; the metadata guard |
| S2 | Search core & endpoint | semantic, api | `store.py` startup-load → numpy matrix + metadata assertion; `search.py` cosine top-k (pure, tested); `/v1/semantic-search` (`q`, `limit`, `translation`, `min_score`, `include_text`), search-in-WEB / hydrate-any-translation via `bible-core`, response shaping, body-hash ETag. | S1, v1 read API | Search correctness; the cross-translation hydrate join; response shape |
| S3 | Docker & deploy | all | Dockerfile fetches the model + runs `build_embeddings` to bake `embeddings.db`; runtime image installs `bible-semantic` + onnxruntime; offline-at-runtime preserved; compose updated; two-tier requirements pinned; **verify `--network none` semantic search works**; record image size + build time in dev-notes. | S2 | Image self-containment; **offline** query; size/footprint |
| S4 | Documentation | repo | README + `docs/API.md`: the semantic-search endpoint, the IBM Granite Apache-2.0 model attribution, the two-tier requirements table; update "what it doesn't do (yet)" (semantic search now done → geography becomes the frontier). | S3 | Accuracy; attribution; tone (match v1's voice) |

**Flagged combined slice — S2.** The cosine search function, the startup vector-load, and
the endpoint are one cycle rather than three. Reason: the endpoint is thin once the search
function and the in-memory matrix exist (parse params → embed query → top-k → hydrate →
shape), and the response-shaping plus the cross-translation hydrate join is the actual
substance — splitting would either duplicate that shaping or merge a half-built search
path. Same reasoning as v1's combined Slice 4. Every other v2 slice stays at the smallest
load-bearing unit.

**Ordering note.** S0 and S1 are sequential (S1 needs S0's embedding function). S2 needs a
populated `embeddings.db` from S1 and the v1 read API for hydration. S3 and S4 follow as
deploy + docs, mirroring v1's tail.
