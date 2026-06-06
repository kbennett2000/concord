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
`embed_query()` (bible-semantic), measured at ~42 ms warm on AVX2 and ~92 ms on the AVX-only
Optiplex. The ONNX session is a single process-cached instance that releases the GIL during
inference, so concurrent requests genuinely contend for CPU cores.

There is currently **no bound on concurrent or repeated calls**. Concord is read-only,
unauthenticated, and trusted-LAN by design (see [docs/SECURITY.md](../SECURITY.md)); behind a
reverse proxy, many clients can share one apparent IP. The realistic availability risk is
therefore **CPU saturation on a single shared box** — from a tight loop or an accidental
client retry storm — not a per-identity abuse problem. The cheap FTS5 `/search`, the in-memory
cosine top-k, and every other endpoint are not the concern; only the model inference is.

## Options considered

### (a) App-level concurrency cap
A bounded semaphore limits the number of simultaneous in-flight inferences; when full, the
request is shed immediately (non-blocking) with `503` + `Retry-After`.

- **For:** directly bounds the scarce resource (CPU); deployment-agnostic — protects
  `make run`, `docker compose`, and a behind-a-proxy deployment alike; needs no client
  identity; tiny state (one semaphore); fails fast and cheap instead of letting requests pile
  up. Naturally inert when semantic search is disabled (the handler already returns 503 before
  any inference) or when the cap is turned off.
- **Against:** the cap is global, not per-client — one abuser can consume it and cause 503s
  for others. But the box stays responsive (graceful degradation), which is the goal. It
  bounds concurrent *compute*, not request *rate*.

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

### (c) Reverse-proxy responsibility
Document rate-limiting at nginx/Caddy and keep the app pure.

- **For:** zero app complexity; the conventional layer for rate/abuse controls in production;
  consistent with SECURITY.md's "before exposing to the public internet" checklist.
- **Against:** it is guidance, not a guarantee — `make run` and the default `docker compose`
  deployment have no proxy and would be unprotected. Proxy rate-limiting also bounds request
  *rate*, not concurrent in-flight *compute*, so it is a weaker fit for the CPU-saturation
  risk specifically.

## Decision

Adopt **(a) an app-level concurrency cap** as the load-bearing protection, complemented by
**(c)** as documented operator guidance. **Reject (b)** as the primary mechanism: client
identity is unreliable on a trusted LAN behind a proxy, it adds state, and it does not
directly bound the CPU that is actually at risk. Per-client fairness, if it is ever needed,
can be added at the proxy later without changing the app.

This matches the threat model: the in-process concurrency cap is the guarantee that always
holds, on every deployment, against the real failure mode (CPU saturation); the proxy note is
defense-in-depth for operators who expose Concord more widely.

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
  an integer, **default `4`**, with `0` meaning disabled (no cap). Rationale for `4`: a single
  inference already spreads across cores, so a small ceiling permits modest legitimate
  concurrency on a weak shared box (the Optiplex) while turning a tight loop / retry storm into
  instant, cheap 503s instead of unbounded oversubscription. Tune up on bigger boxes, down on
  tiny ones.
- **Observability:** shed events are logged via the existing structured logger,
  `structlog.get_logger("bible_api").warning("concord.api.semantic_shed", limit=…)`.
- **Interaction with `CONCORD_SEMANTIC_SEARCH=0`:** inert. With semantic disabled the store is
  `None` and the handler raises `SemanticUnavailableError` before reaching the semaphore, so
  the cap is never engaged and no model is loaded. With the cap itself set to `0`, no guard is
  applied. The FTS5 `/search` path and all other endpoints are untouched in every case.

## Consequences

- **Positive:** CPU is bounded to at most *N* concurrent inferences regardless of deployment
  or client behavior; the box degrades gracefully (a fast 503 + `Retry-After`) rather than
  melting down; no new dependency and no client-identity machinery; the pure-library boundary
  is preserved (the guard lives entirely in bible-api).
- **Negative / accepted:** the protection is global, not per-client — a single abuser can
  still cause others' requests to be shed. This is accepted: keeping the box available is the
  goal. A too-low cap could 503 legitimate bursts; this is mitigated by the env knob and a
  sensible default.
- **Testability:** the behavior is asserted deterministically (no timing-based flakiness) by
  injecting a stub semantic store and no-op `embed_query`/`cosine_top_k` so the fast suite
  reaches the guard without the real model, then deterministically occupying the permit
  (cap = 1 with the permit pre-held, or a forced non-blocking-acquire failure) and asserting
  503 + the `semantic_busy` envelope + `Retry-After`; a request under the cap returns 200. The
  existing integration tests continue to cover the real inference path.
- **Operator note:** README/SECURITY.md will note that production deployments may add
  proxy-level rate-limiting in front for defense-in-depth; the app-level cap is the in-process
  guarantee that always holds.
