# Vendored interactive-docs assets

These third-party static assets are committed so `/docs` (Swagger UI) and `/redoc` render
**fully offline** — no CDN reach at runtime (SPEC §3). They ship inside the `bible_api`
wheel and are served from `/static/…`. To upgrade, re-download the same filenames from a
pinned version and bump the versions below (a deliberate, reviewed change).

| Asset | Source | Version | License |
|---|---|---|---|
| `swagger-ui/swagger-ui-bundle.js`, `swagger-ui/swagger-ui.css`, `swagger-ui/favicon-32x32.png` | [swagger-ui-dist](https://www.npmjs.com/package/swagger-ui-dist) (jsDelivr) | 5.32.6 | Apache-2.0 |
| `redoc/redoc.standalone.js` | [redoc](https://www.npmjs.com/package/redoc) (jsDelivr) | 2.5.3 | MIT |
