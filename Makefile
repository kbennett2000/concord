# Concord dev tasks. Every check is one command from the repo root, over both packages.
.PHONY: install lint fmt fmt-check typecheck test check run build-db \
        docker-build docker-up docker-down docker-verify

install:           ## Create the shared .venv and editable-install both packages
	uv sync

lint:              ## Ruff lint
	uv run ruff check .

fmt:               ## Ruff format (write)
	uv run ruff format .

fmt-check:         ## Ruff format (check only)
	uv run ruff format --check .

typecheck:         ## Pyright (strict)
	uv run pyright

test:              ## Pytest (both packages; excludes integration)
	uv run pytest

check: lint fmt-check typecheck test  ## Run the full gate

run:               ## Run the API locally (honors BIBLE_API_PORT, default 8000)
	uv run uvicorn bible_api.app:app --host 0.0.0.0 --port $${BIBLE_API_PORT:-8000}

build-db:          ## Build bible.db from data/translations (+ local data/private)
	uv run python -m bible_core.loader

# --- Docker (operator) ------------------------------------------------------------------

docker-build:      ## Build the production image
	docker compose build

docker-up:         ## Start the service (detached)
	docker compose up -d

docker-down:       ## Stop the service
	docker compose down

docker-verify:     ## Post-deploy checks against the running container
	@PORT=$${BIBLE_API_PORT:-8000}; \
	echo "healthz:"; \
	curl -fsS "http://localhost:$$PORT/healthz" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['translation_count']>0 and d['verse_count']>0, d; print('  ok', d)"; \
	echo "random:"; \
	curl -fsS "http://localhost:$$PORT/v1/random" >/dev/null && echo "  ok"; \
	echo "offline /docs (no CDN):"; \
	if curl -fsS "http://localhost:$$PORT/docs" | grep -Eq "jsdelivr|unpkg|fonts.googleapis"; then \
	  echo "  FAIL: /docs reaches a CDN"; exit 1; else echo "  ok (no CDN URLs)"; fi
