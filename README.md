# Concord

A self-hosted, LAN-first, **read-only** Scripture API serving multiple public-domain Bible
translations — verse/range/chapter fetch, multi-translation parallel reads, full-text
search, cross-references, and metadata — from one canonical SQLite source. Runs 100%
offline after build.

> **Operator README.** Enough to build, run, and deploy. The warm, full guide arrives in
> Slice 9. Design lives in [`docs/SPEC.md`](docs/SPEC.md).

## Requirements

- Docker + Docker Compose (v2).
- A host on your LAN. The API is unauthenticated and intended for trusted networks only —
  do not expose it to the public internet.

## Quick start

```bash
git clone https://github.com/kbennett2000/concord.git
cd concord
docker compose up -d --build          # builds the image (bakes bible.db) and starts the API
curl http://localhost:8000/healthz    # -> {"status":"ok","translation_count":13,...}
```

Interactive docs (fully offline): <http://localhost:8000/docs> (Swagger UI) and
<http://localhost:8000/redoc>.

A few requests:

```bash
curl 'http://localhost:8000/v1/verses/John%203:16?translations=kjv,web'
curl 'http://localhost:8000/v1/search?q=lamp%20unto%20my%20feet&translation=KJV'
curl 'http://localhost:8000/v1/cross-references/John%203:16?include_text=true&translation=KJV'
curl 'http://localhost:8000/v1/random?testament=OT'
curl 'http://localhost:8000/v1/books'
curl 'http://localhost:8000/v1/translations'
```

## Configuration

Copy [`.env.example`](.env.example) to `.env` and edit, or set these in the host
environment — `docker compose` reads both. None are required (all have defaults).

| Variable | Default | Meaning |
|---|---|---|
| `BIBLE_API_PORT` | `8000` | Host port the API is published on (container always listens on 8000). |
| `CONCORD_CORS_ORIGINS` | `*` | Comma-separated allowed CORS origins. `*` suits LAN use. |
| `CONCORD_DEFAULT_TRANSLATION` | `KJV` | Translation used when `?translation(s)=` is omitted. Must be loaded, or the API refuses to start. |
| `BIBLE_DB_PATH` | `/app/bible.db` | Path to the baked database inside the container. |

Changing the port is a one-line edit:

```bash
BIBLE_API_PORT=9001 docker compose up -d    # now on http://localhost:9001
```

## Deploying to a LAN host

The database is **baked into the image** at build time, so deploying is "ship the repo,
build, run" — no volumes, no separate data step. Replace `bible.example.lan` with your host.

```bash
rsync -a --exclude .git --exclude data/private ./ user@bible.example.lan:~/concord/
ssh user@bible.example.lan 'cd ~/concord && docker compose up -d --build'
```

Then from any LAN client: `curl http://bible.example.lan:8000/healthz`.

(Private, non-distributable translations in `data/private/` are gitignored and excluded
above; the image bakes only the committed public-domain translations.)

## Verifying the deployment

```bash
make docker-verify          # healthz counts, /v1/random, and /docs has no CDN URLs
docker compose ps           # STATUS shows "healthy" within ~10s of starting
```

**Offline check (the point of this project).** The image carries every asset it needs,
including the Swagger UI / ReDoc bundles — `/docs` works with no internet:

```bash
docker run --rm --network none -p 8000:8000 concord:latest &   # no network at all
sleep 5
curl -s http://localhost:8000/docs | grep -Eq 'jsdelivr|unpkg|fonts.googleapis' \
  && echo 'FAIL: reaches a CDN' || echo 'OK: /docs is fully self-hosted'
```

Or: disconnect the host from the internet, open `http://<host>:8000/docs` in a browser —
Swagger UI renders fully.

## Stopping

```bash
docker compose down
```

## Troubleshooting

- **`bind: address already in use`** — the port is taken; set `BIBLE_API_PORT` to a free one.
- **Container stuck `unhealthy` / restarting** — `docker compose logs api`. The API refuses
  to start if `bible.db` is missing or `CONCORD_DEFAULT_TRANSLATION` isn't a loaded
  translation; the startup log line names the cause.
- **`/docs` renders blank** — the vendored Swagger UI bundle didn't make it into the image
  (e.g. a broken custom build). Confirm `curl .../static/swagger-ui/swagger-ui-bundle.js`
  returns 200.

## License & attribution

MIT © 2026 Kris Bennett — see [`LICENSE`](LICENSE). Cross-reference data courtesy of
[OpenBible.info](https://www.openbible.info/labs/cross-references/) under CC BY. Translation
provenance is in [`data/SOURCES.md`](data/SOURCES.md).
