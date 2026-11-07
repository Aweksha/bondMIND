.PHONY: up down reset-demo backend-setup api web test lint seed-generate

up:            ## Start the full stack (db + api + web) at http://localhost:8080
	docker compose up -d --build --wait

down:
	docker compose down

reset-demo:    ## Wipe and reload seeded demo data
	docker compose exec api python -m app.seed.load --reset

backend-setup:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

api:           ## Run the API locally against the compose database
	docker compose up -d db --wait
	cd backend && .venv/bin/alembic upgrade head && .venv/bin/python -m app.seed.load && \
	  .venv/bin/uvicorn app.main:app --reload

web:           ## Run the Angular dev server (proxies /api to :8000)
	cd frontend && npx ng serve

seed-generate: ## Regenerate synthetic CSV snapshots (deterministic)
	cd backend && .venv/bin/python -m app.seed.generate

test:
	cd backend && .venv/bin/pytest
	cd frontend && npx ng test --watch=false

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npx prettier --check "src/**/*.{ts,html,scss}"
