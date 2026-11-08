.PHONY: export pages-preview up down reset-demo backend-setup api web test e2e lint seed-generate refresh-curve

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

export:        ## Pre-compute the website's data files into frontend/public/data
	cd backend && .venv/bin/python -m app.export.static_site ../frontend/public/data

web: export    ## Run the Angular dev server on :4200
	cd frontend && npx ng serve

pages-preview: export ## Build exactly what GitHub Pages serves and preview it on :8095
	cd frontend && npx ng build --base-href /bondMIND/ && cp dist/frontend/browser/index.html dist/frontend/browser/404.html && node e2e/pages-server.mjs dist/frontend/browser 8095

seed-generate: ## Regenerate synthetic CSV snapshots (deterministic)
	cd backend && .venv/bin/python -m app.seed.generate

test:
	cd backend && .venv/bin/pytest
	cd frontend && npx ng test --watch=false

e2e:           ## Browser tests against the running stack (make up first)
	cd frontend && npx playwright test

refresh-curve: ## Download the latest U.S. Treasury par curve snapshot
	cd backend && .venv/bin/python -m app.ingest.ust_treasury --from-year 2019

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npx prettier --check "src/**/*.{ts,html,scss}"
