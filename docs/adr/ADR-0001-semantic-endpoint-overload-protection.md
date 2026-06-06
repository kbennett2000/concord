# ADR-0001: Semantic-endpoint overload protection

**Status:** Proposed

<!--
ADR format for this repo (the first one — establishes the template): a short title line, a
Status, then Context / Options considered / Decision / Consequences. Status values:
Proposed → Accepted → (later) Superseded by ADR-NNNN. Keep each ADR to one decision.
-->

## Context

`/v1/semantic-search` (`semantic_search_endpoint` in
[bible-api/src/bible_api/routers.py](../../bible-api/src/bible_api/routers.py), a synchronous
`def` that FastAPI runs in its threadpool) performs an ONNX forward pass per request via
`embed_query()` (bible-semantic).

**The supported deployment baseline is older, cheap, non-AVX2 hardware** — AVX2 is a
nice-to-have, not the baseline. On AVX2 a warm pass is ~40–92 ms, **but on the non-AVX2 boxes
that are the real target, ONNX Runtime falls back to a generic path and a single forward pass
can take hundreds of milliseconds to several seconds.** The ONNX session is a single
process-cached instance with default threading (no `SessionOptions` tuning,
[model.py](../../bible-semantic/src/bible_semantic/model.py)), so a single inference already
spreads across all cores and concurrent inferences contend for them.

There is currently **no bound on concurrent or repeated calls**. Concord is read-only,
unauthenticated, and trusted-LAN by design (see [docs/SECURITY.md](../SECURITY.md)); behind a
reverse proxy, many clients can share one apparent IP. On slow hardware there are **two
distinct availability risks**:

1. **Too many inferences at once** — a tight loop or an accidental client retry storm piling
   up concurrent forward passes, saturating CPU on a single shared box.
2. **One inference that is simply slow** — a multi-second pass during which a caller may time
   out and retry, adding *another* slow pass, and so on.

The cheap FTS5 `/search`, the in-memory cosine top-k, and every other endpoint are not the
concern; only the model inference is.

## Options considered

### (a) App-level concurrency cap
A bounded semaphore limits the number of simultaneous in-flight inferences; when full, the
request is shed immediately (non-blocking) with `503` + `Retry-After`.

- **For:** directly bounds the scarce resource (CPU); deployment-agnostic — protects
  `make run`, `docker compose`, and a behind-a-proxy deployment alike; needs no client
  identity; tiny state (one semaphore); fails fast and cheap instead of letting requests pile
  up. Naturally inert when semantic search is disabled (the handler already 503s before any
  inference) or when the cap is turned off.
- **Against:** the cap is global, not per-client — one abuser can consume it and cause 503s
  for others (accepted: the box stays responsive, which is the goal). It bounds concurrent
  *compute*, not request *rate*, and **not the duration of any single inference** (addressed
  in the Decision).

### (b) App-level per-client rate limit
A token-bucket / quota keyed by client, returning `429` when exceeded.

- **For:** limits per-source abuse and is "fair" across clients — *when client identity is
  reliable*.
- **Against:** identity is **unreliable on a trusted LAN behind a proxy**: clients share the
  proxy's apparent IP, so either everyone is throttled together, or you trust a spoofable
  `X-Forwarded-For` with no auth to anchor it. It adds per-client state (buckets, eviction).
  Most importantly, it does **not** directly bound CPU — many distinct clients each under their
  own limit can still saturate the box. More complexity, weaker guarantee against the actual
  risk.

### (c) Reverse-proxy / client responsibility
Document rate-limiting **and request timeouts** at nginx/Caddy/the client; keep the app pure.

- **For:** zero app complexity; the conventional layer for rate *and timeout* controls; the
  only layer that can actually give up on an uncancelable slow upstream; consistent with
  SECURITY.md's "before exposing to the public internet" checklist.
- **Against:** it is guidance, not a guarantee — `make run` and the default `docker compose`
  deployment have no proxy and would be unprotected. It bounds request *rate* / caller *wait*,
  not concurrent in-flight *compute*.

## Decision

Adopt **(a) an app-level concurrency cap** as the load-bearing protection, complemented by
**(c)** as documented operator guidance (now explicitly including a request-timeout note).
**Reject (b)** as the primary mechanism: client identity is unreliable on a trusted LAN behind
a proxy, it adds state, and it does not directly bound the CPU that is actually at risk.
Per-client fairness, if it is ever needed, can be added at the proxy later without changing the
app.

This matches the (revised) threat model: the in-process concurrency cap is the guarantee that
always holds, on every deployment and on slow hardware, against risk (1); risk (2) — a single
slow inference — is bounded at the client/proxy because the inference itself is uncancelable
(see below).

### Concrete shape (the contract the implementation must meet)

- **Where:** a process-global bounded semaphore lives in **bible-api** (the web layer —
  bible-semantic stays a pure, web-free embeddable library). It is created in `create_app()`
  from config and stored on `app.state` (per-app, so it is test-configurable). It wraps only
  the expensive compute (`cosine_top_k(embed_query(q), …)`); the cheap text hydration (DB
  reads) stays outside the guard.

- **Over-cap response:** a non-blocking acquire; on failure raise a new `SemanticBusyError` →
  **HTTP 503** in the standard error envelope
  `{"error": {"code": "semantic_busy", "message": …, "detail": {}}}`, with a **`Retry-After: 1`**
  header. `503` (not `429`) because the limit is global server *capacity*, not a per-client
  quota — and it matches the existing `SemanticUnavailableError` → 503 precedent in
  [errors.py](../../bible-api/src/bible_api/errors.py). (`_error_response` gains an optional
  `headers` parameter — a one-line, backward-compatible change — to carry `Retry-After`.)

- **Env knob** (mirroring `config.semantic_enabled()`): `CONCORD_SEMANTIC_MAX_CONCURRENCY`,
  an integer, **default `2`**, with `0` meaning disabled (no cap). The default is sized to the
  **weakest supported box** — roughly **one in-flight inference per core** on a 2-core,
  non-AVX2 machine — because the default is what runs when nobody tunes the env var, and the
  cheap-hardware operators are exactly the ones least likely to tune it. `4` would be 2×
  oversubscription on that box (multi-second inferences thrashing two cores the cap never
  protects); `1` is full serialization for a truly minimal box; operators on bigger boxes tune
  up. **Note:** the cap bounds the *number* of concurrent inferences, not core reservation —
  ONNX's default intra-op threading makes a *single* inference use *all* cores, so headroom for
  the cheap endpoints during an inference comes from OS time-slicing, not a reserved core.
  (Reserving a core by capping ONNX intra-op threads is rejected: it would live in the pure
  library and would further slow each query on already-slow hardware.)

- **Single-query slowness — no in-app inference deadline.** This is a deliberate decision, not
  an omission. An ONNX `session.run()` is **not cleanly cancelable** and Python threads cannot
  be safely killed, so an in-app timeout would be one of two bad things:
  - *Soft* (stop waiting, return an error, but the inference keeps burning CPU): **harmful** —
    it decouples the cap from real CPU usage (more inferences actually running than the cap
    permits) and invites retry amplification.
  - *Hard* (actually stop the CPU work): requires running each inference in a separate
    killable process (multiprocessing + IPC + model memory per worker) — disproportionate
    complexity for a LAN tool, and it does not make a slow box fast.

  The concurrency cap already converts the retry cascade into "**at most N slow inferences
  running + instant cheap 503s for everyone else**" — it bounds *how many* slow inferences run
  concurrently. Bounding *how long a caller waits* is delegated to a **client / reverse-proxy
  read-timeout**, the only layer that can abandon an uncancelable upstream. (ONNX Runtime has a
  cooperative `RunOptions.terminate` flag that a per-request watchdog could set; it aborts only
  at operator boundaries and adds real wiring — noted as a deliberately **deferred** option if
  a hard server-side deadline is ever justified.)

- **Observability:** shed events are logged via the existing structured logger,
  `structlog.get_logger("bible_api").warning("concord.api.semantic_shed", limit=…)`.

- **Interaction with `CONCORD_SEMANTIC_SEARCH=0`:** inert. With semantic disabled the store is
  `None` and the handler raises `SemanticUnavailableError` before reaching the semaphore, so
  the cap is never engaged and no model is loaded. With the cap itself set to `0`, no guard is
  applied. The FTS5 `/search` path and all other endpoints are untouched in every case.

## Consequences

- **Positive:** concurrent inferences are bounded to at most *N* regardless of deployment or
  hardware; the box degrades gracefully (a fast 503 + `Retry-After`) rather than melting down;
  no new dependency and no client-identity machinery; the pure-library boundary is preserved
  (the guard lives entirely in bible-api).
- **Negative / accepted:** the protection is global, not per-client — a single abuser can
  still cause others' requests to be shed (accepted: keeping the box available is the goal). A
  too-low cap could 503 legitimate bursts (mitigated by the env knob). The app does **not**
  bound single-inference duration or protect a caller hanging on the socket — that is
  deliberately the client/proxy's job, because the inference is uncancelable; without such a
  timeout a caller on slow hardware may wait seconds for a response.
- **Testability:** the behavior is asserted deterministically (no timing-based flakiness) by
  injecting a stub semantic store and no-op `embed_query`/`cosine_top_k` so the fast suite
  reaches the guard without the real model, then deterministically occupying the permit
  (cap = 1 with the permit pre-held, or a forced non-blocking-acquire failure) and asserting
  503 + the `semantic_busy` envelope + `Retry-After`; a request under the cap returns 200. The
  existing integration tests continue to cover the real inference path.
- **Operator note:** README/SECURITY.md will recommend a reverse proxy with **rate-limiting
  and a request read-timeout** for production / public exposure — the proxy is where caller
  wait-time is bounded; the app-level cap is the in-process CPU guarantee that always holds.
- **Related, deferred (not decided here):** on RAM-constrained cheap hardware the S3b 2 GB
  compose memory limit may need revisiting — int8 model + ~95 MB vector matrix + ORT arena +
  Python could approach it, and OOM-kill is a *separate* availability risk from CPU
  saturation. A future check (measure RSS on a cheap box), out of scope for this ADR.
