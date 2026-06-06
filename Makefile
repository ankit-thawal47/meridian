.PHONY: install up down api worker test lint typecheck fmt

install:
	uv venv && uv pip install -e '.[dev]'

up:        ## start postgres + redis (+ api + worker) locally
	docker compose up -d postgres redis

down:
	docker compose down

api:       ## run the FastAPI control plane
	uvicorn meridian.main:app --reload --app-dir src

worker:    ## run an arq agent worker
	arq meridian.worker.runner.WorkerSettings

test:
	pytest -q

lint:
	ruff check src tests

typecheck:
	mypy src

fmt:
	ruff format src tests && ruff check --fix src tests
