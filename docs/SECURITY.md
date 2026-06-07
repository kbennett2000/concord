# Security

## Threat model — what Concord is built for

Concord is designed for **one deployment shape: a trusted LAN**. It is a **read-only**
Scripture API with **no authentication** (the LAN is the trust boundary), **no writes** (the
corpus is immutable and baked into the image), and **no internet dependency at runtime** (no
CDNs, no telemetry, no phone-home). Within that shape, the design assumes every client that
can reach the port is allowed to read Scripture data — which is public-domain anyway.

Because the data is read-only and public, the realistic risks on a LAN are availability
(resource amplification) and operator misconfiguration, not data confidentiality or
tampering. The hardening in place reflects that:

- **Read-only at every layer.** `bible.db` is opened SQLite `mode=ro`; the semantic vectors
  are read once at boot. Nothing the request path can do writes to disk.
- **Runs as a non-root user.** The container drops to an unprivileged user (uid 999) before
  starting, so a process compromise doesn't begin as root.
- **Bounded inputs.** Reference and query lengths are capped, and the reference parser caps
  verse-list size, so a single cheap request can't fan out to unbounded compute or SQL.
- **Semantic-search overload protection.** `/v1/semantic-search` runs an ONNX inference per
  request, governed by two in-process bounds: a concurrency cap on how *many* run at once
  (`CONCORD_SEMANTIC_MAX_CONCURRENCY`, default 2) and a wall-clock deadline on how *long* one
  may run (`CONCORD_SEMANTIC_TIMEOUT_S`, default 10s), each shedding with `503` + `Retry-After`.
  Together they keep a loop/retry storm or a single slow query from tying up the box (see the
  subsection below and ADR-0001 / ADR-0002).
- **`X-Content-Type-Options: nosniff`** on every response. No CSP — it isn't needed for a
  JSON API and would risk the vendored offline docs for little gain.
- **Offline by construction.** All assets (database, model, vectors, Swagger UI / ReDoc) are
  baked into the image; the runtime makes no outbound network calls.

## Semantic search: overload and single-request latency

`/v1/semantic-search` performs an ONNX forward pass per request — the one compute-heavy path.
Two distinct risks, handled at two layers:

- **Too many at once** — the app's concern. A concurrency cap
  (`CONCORD_SEMANTIC_MAX_CONCURRENCY`, default **2**, sized to a weak ~2-core non-AVX2 box)
  bounds simultaneous inferences and sheds the excess immediately with `503` + `Retry-After`.
  This is an in-process guarantee that holds on every deployment.

- **One request that is slow** — now **partly the app's concern too** (ADR-0002). A
  server-side wall-clock deadline (`CONCORD_SEMANTIC_TIMEOUT_S`, default **10s**, `0` disables)
  bounds how long a caller waits: the inference runs in a small executor and, if it overruns the
  budget, the request is shed with `503` + `Retry-After`. Crucially, the deadline bounds *caller
  wait*, not *CPU* — an ONNX `session.run()` is not cleanly cancelable (see ADR-0001), so the
  timed-out inference keeps running to completion and keeps holding its concurrency permit until
  it does. That is deliberate: it keeps the cap coupled to real CPU, so a retry after a timeout
  hits a full cap and is shed (`semantic_busy`) rather than stacking a second slow pass.

  **Still set a client / reverse-proxy read-timeout as defense-in-depth.** The in-app deadline
  does not cover a stalled network read, a slow-loris client, or a deployment that has turned the
  cap or the deadline off — and a proxy is the only layer that can abandon a genuinely stuck
  upstream socket. On non-AVX2 hardware especially, treat the proxy read-timeout as belt to the
  app's braces, not as redundant.

See [`docs/adr/ADR-0001`](adr/ADR-0001-semantic-endpoint-overload-protection.md) and
[`docs/adr/ADR-0002`](adr/ADR-0002-semantic-endpoint-deadline.md) for the decisions and
tradeoffs.

## CORS — why it's permissive on purpose

CORS allows all origins (`CONCORD_CORS_ORIGINS` defaults to `*`) with **credentials
disabled** (`allow_credentials=False`). This is the correct configuration for this service,
not an oversight:

- The API is **read-only and unauthenticated** — there are no cookies, sessions, or tokens
  for a malicious origin to ride on. A browser on the LAN reading public Scripture data
  cross-origin exposes nothing that isn't already openly readable.
- Disabling credentials is what *keeps* the `*` origin safe: the browser will never attach
  ambient credentials to these requests, so there's no CSRF-style risk to abuse.
- Operators who want to narrow it (e.g. to a single internal app's origin) can set
  `CONCORD_CORS_ORIGINS` — but on a trusted LAN the default is appropriate.
- Cacheable (immutable) responses carry `Vary: Origin` so a copy cached by a no-`Origin`
  navigation isn't replayed to a later cross-origin `fetch` (which would fail its CORS check
  on the cached response). This is purely cache-correctness — the posture above is unchanged.

## Before exposing Concord to the public internet

Concord is **not designed to be a public, internet-facing service**, and nothing here should
be read as a claim that it is hardened for that. If you put it on the public internet,
**add these in front of it first** — they are deliberately out of Concord's scope:

- **A reverse proxy terminating TLS** (Concord speaks plain HTTP; it expects a trusted
  network or a proxy to handle transport security).
- **Authentication / authorization** at the proxy — Concord has none by design.
- **Rate limiting and a request read-timeout** at the proxy. Rate limiting bounds abuse
  beyond Concord's input caps and concurrency cap; the **read-timeout** is defense-in-depth
  behind the app's own semantic deadline (`CONCORD_SEMANTIC_TIMEOUT_S`) — it still covers a
  stalled socket, a slow-loris client, or a deployment with the deadline turned off (see the
  semantic subsection above). It matters most on non-AVX2 hardware.
- **A restrictive `CONCORD_CORS_ORIGINS`** naming only the origins you actually serve.
- **Network controls** (firewall/ACLs) limiting who can reach the port at all.

## Reporting a vulnerability

This is a self-hosted, single-purpose project. If you find a security issue, please open a
GitHub issue (omit any sensitive exploit details from the public description and offer to
share them privately).
