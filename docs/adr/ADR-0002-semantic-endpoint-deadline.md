# ADR-0002: Semantic-endpoint wall-clock deadline

**Status:** Accepted

<!--
Extends ADR-0001 (semantic-endpoint overload protection). ADR-0001 bounded *how many*
inferences run at once and deliberately deferred bounding *how long* a single one runs; this
ADR adds that second bound. Format mirrors ADR-0001: Context / Options considered / Decision /
Consequences.
-->

## Context

[ADR-0001](ADR-0001-semantic-endpoint-overload-protection.md) added a concurrency cap to
`/v1/semantic-search` (`semantic_search_endpoint` in
[bible-api/src/bible_api/routers.py](../../bible-api/src/bible_api/routers.py)): a bounded
semaphore limits how *many* ONNX inferences run at once and sheds the excess with `503` +
`Retry-After`. It named **two** distinct availability risks on the supported slow, non-AVX2
hardware baseline, and solved only the first:

1. **Too many inferences at once** — solved by the cap.
2. **One inference that is simply slow** — *not* bounded by the app. ADR-0001 delegated this
   entirely to a client / reverse-proxy read-timeout, on the reasoning that an ONNX
   `session.run()` is not cleanly cancelable and Python threads cannot be safely killed, so any
   in-app deadline would be either a *soft* timeout (stop waiting but let the inference keep
   burning CPU — **harmful**, because it decouples the cap from real CPU and invites retry
   amplification) or a *hard* one (a killable subprocess — disproportionate for a LAN tool).

That left a real gap: on `make run` and the default `docker compose` deployment — neither of
which has a proxy — **nothing bounds how long a caller waits**. On a non-AVX2 box a single pass
can take several seconds, and a caller that gives up and retries adds *another* slow pass. The
"set a proxy read-timeout" guidance is the right belt, but it is guidance, not a guarantee, and
the operators least likely to put a proxy in front are exactly the cheap-hardware operators who
need the protection most.

This ADR adds a **server-side wall-clock deadline** that closes the gap **without**
reintroducing the CPU-decoupling problem ADR-0001 warned about. The key realization: a soft
timeout is only harmful if it *also releases the concurrency permit early*. If the permit stays
held until the inference truly finishes, the deadline bounds *caller wait* while the cap
continues to bound *CPU* — the two concerns stay separate and never decouple.

## Options considered

### (a) Executor with the permit held by the worker — *chosen*
Run `embed_query(q)` + `cosine_top_k(...)` in a small `ThreadPoolExecutor`; the handler waits
with `future.result(timeout=T)` and, on `TimeoutError`, sheds the request. **The permit is
acquired in the handler before submit but released inside the worker — never in the handler** —
so a timed-out ("zombie") inference keeps holding its slot until it completes.

- **For:** bounds caller wait on every deployment with no proxy required; keeps the cap coupled
  to real CPU (a retry after a timeout hits a full cap and is shed `semantic_busy`, never
  stacking a second slow pass); no new dependency (`concurrent.futures` is stdlib); the pure
  library is untouched — the executor, deadline, and exception all live in `bible-api`, so
  `bible-semantic` stays web-free and the cosine/embed core stays pure; deterministically
  unit-testable without the real model by injecting a blocking callable.
- **Against:** a timed-out inference still runs to completion, so the deadline saves *wait*, not
  *CPU* (accepted — the cap is what bounds CPU, and that still holds); two threads are in play
  per in-flight request during inference (the FastAPI threadpool thread waiting + the executor
  thread computing). Bounded by pinning `max_workers` to the cap (see Decision).

### (b) Cooperative `RunOptions.terminate`
ONNX Runtime exposes a cooperative `RunOptions.terminate` flag a watchdog could set to abort a
run at operator boundaries.

- **For:** would actually free CPU, not just caller wait.
- **Against:** requires threading a per-request `RunOptions` through
  `bible_semantic.model.embed_query`, making the pure ONNX core session-aware and stateful —
  violating the "cosine/embed core stays pure" invariant. Aborts only at operator boundaries
  (coarse, still not a hard bound) and is untestable without the real model. ADR-0001 already
  flagged it as deliberately **deferred**; it stays deferred.

### (c) Hard timeout via a killable subprocess
Run each inference in a separate process that can be killed on deadline.

- **For:** a true hard bound on both wait and CPU.
- **Against:** multiprocessing + IPC + model memory per worker (or a shared-memory vector
  store) — disproportionate complexity for a LAN tool, and it does not make a slow box fast.
  Rejected in ADR-0001; unchanged here.

### (d) Naive soft timeout (release the permit on timeout)
Stop waiting, return an error, release the permit immediately, let the inference run on.

- **Against:** this is exactly the option ADR-0001 rejected — it decouples the cap from CPU
  (more inferences actually running than the cap permits) and invites retry amplification.
  Rejected.

## Decision

Adopt **(a)**: a per-app `ThreadPoolExecutor` runs the inference, the handler bounds its wait
with `future.result(timeout=T)`, and **the permit is released by the worker, never the
handler**, so a timed-out inference keeps its slot until it finishes. Reject (b), (c), (d) for
the reasons above; (b) remains the deferred path if a hard CPU bound is ever justified.

### Concrete shape (the contract the implementation meets)

- **Where:** the executor and timeout live on `app.state` in **bible-api**, created in
  `create_app()` from config (test-overridable via a `semantic_timeout_s` param, mirroring
  `semantic_max_concurrency`). `bible-semantic` is untouched.

- **Ordering & release:** acquire the permit (non-blocking, shed `semantic_busy` on failure —
  ADR-0001, unchanged) → submit `_run_inference` to the executor → `future.result(timeout)`.
  `_run_inference` releases the permit in a `finally`, so the semaphore has exactly one owner
  and is released exactly once on every path (success, error, or post-timeout completion).

- **Over-deadline response:** on `concurrent.futures.TimeoutError`, raise a new
  `SemanticTimeoutError` → **HTTP 503** in the standard envelope
  `{"error": {"code": "semantic_timeout", "message": …, "detail": {}}}`, with `Retry-After: 1`.
  **503, not 504:** Concord is the origin doing its own compute, not a gateway awaiting an
  upstream (504's intended role), and a deadline breach almost always means the box is genuinely
  overloaded — the same "retry shortly" condition as `semantic_busy`, so a client's backoff
  handles both uniformly. The distinct `code` keeps "ran too long" separable from "shed before
  running" in logs.

- **Env knob:** `CONCORD_SEMANTIC_TIMEOUT_S`, a float, **default `10.0`**, with `0` (or any
  non-positive value) meaning disabled. The default sits comfortably above a legitimately slow
  single query on the weakest supported box ("several seconds", ADR-0001), so it fires only on a
  pathological / hung pass — never on honest traffic — while still capping the unbounded case.

- **`max_workers` is pinned to the cap.** Because the permit is acquired *before* submit, a
  request with no permit is shed before it can submit, so the number of concurrently-running
  workers can never exceed the cap. Sizing the executor to the cap makes executor depth track
  the cap exactly — no unbounded thread growth even under a timeout storm — and needs no
  separate knob.

- **Inertness:** the executor is created **only** when a cap is active **and** the timeout is
  positive. With the cap off (`sem is None`) the inference runs inline with no deadline (an
  uncapped box has opted out of this protection — there is no permit to couple to). With the
  timeout off (`0`) but the cap on, the handler keeps ADR-0001's synchronous
  `acquire → run → release` path byte-for-byte. With semantic search disabled the handler raises
  `SemanticUnavailableError` before any of this. The FTS5 `/search` path and all other endpoints
  are untouched.

- **Observability:** timeout events log via the existing structured logger,
  `structlog.get_logger("bible_api").warning("concord.api.semantic_timeout", timeout_s=…)`,
  alongside ADR-0001's `concord.api.semantic_shed`.

## Consequences

- **Positive:** caller wait on `/v1/semantic-search` is now bounded in-process on every
  deployment, with or without a proxy; the cap↔CPU coupling ADR-0001 depends on is preserved
  (the permit is held by the zombie until it drains); no new dependency; the pure-library
  boundary is intact.
- **Negative / accepted:** the deadline bounds *wait*, not *CPU* — a timed-out inference runs to
  completion (the only alternatives that free CPU are the rejected (b)/(c)); during inference two
  threads are used per in-flight request (bounded by `max_workers == cap` and well within
  FastAPI's default threadpool). A too-low timeout could shed legitimate slow queries (mitigated
  by the generous default and the env knob).
- **Defense-in-depth, not replacement:** a client / reverse-proxy read-timeout is **still
  recommended** — it covers a stalled socket, a slow-loris client, and deployments that turn the
  cap or the deadline off, none of which the in-app deadline addresses. README and
  [docs/SECURITY.md](../SECURITY.md) are updated to describe the in-app bound while keeping the
  proxy read-timeout as the belt to the app's braces.
- **Testability:** asserted deterministically (no sleeps, no wall-clock races) by injecting a
  no-op store + an inference callable that blocks on a `threading.Event` the test controls — the
  work never completes, so any positive deadline fires deterministically. The tests cover the
  503 + `semantic_timeout` + `Retry-After` envelope; the cap-coupling proof (a zombie holds its
  permit, so a concurrent request is shed `semantic_busy` and only succeeds after the worker
  drains); and the timeout-off / cap-off inert paths. See
  [bible-api/tests/test_semantic_timeout.py](../../bible-api/tests/test_semantic_timeout.py).
- **Related, deferred (not decided here):** a hard CPU bound via cooperative
  `RunOptions.terminate` (option (b)) remains the path if single-inference *CPU* ever needs
  bounding rather than just caller wait.
