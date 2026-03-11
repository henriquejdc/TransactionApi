.PHONY: help build up down down-v restart logs logs-worker test test-no-cov coverage format lint migrate migration shell \
        clean ps worker api

BIN ?= .venv/bin/python -m

help:
	@echo ""
	@echo "  Transaction API — available commands"
	@echo "  ─────────────────────────────────────────────────────────"
	@echo "  Docker"
	@echo "    make build        Rebuild all images"
	@echo "    make up           Start all services (detached)"
	@echo "    make down         Stop and remove containers"
	@echo "    make down-v       Stop, remove containers and volumes"
	@echo "    make restart      Restart the API container"
	@echo "    make ps           Show status of all containers"
	@echo "    make logs         Tail logs from the API container"
	@echo "    make logs-worker  Tail logs from the worker container"
	@echo ""
	@echo "  Database"
	@echo "    make migrate      Run alembic upgrade head (inside container)"
	@echo "    make migration m='msg'  Auto-generate a new migration"
	@echo ""
	@echo "  Tests"
	@echo "    make test         Run full test suite with coverage"
	@echo "    make coverage     Run coverage report for the full test suite"
	@echo "    make test-no-cov  Run tests without coverage requirement"
	@echo ""
	@echo "  Dev"
	@echo "    make format       Format code with black and isort"
	@echo "    make lint         Check formatting with isort and black"
	@echo "    make shell        Open a shell inside the API container"
	@echo "    make clean        Remove __pycache__ and .pyc files"
	@echo ""

build:
	docker compose build

up:
	docker compose up --build -d

down:
	docker compose down

down-v:
	docker compose down -v

restart:
	docker compose build api && docker compose restart api

ps:
	docker compose ps

logs:
	docker compose logs -f api

logs-worker:
	docker compose logs -f worker

migrate:
	docker compose exec api alembic upgrade head

migration:
	docker compose exec api alembic revision --autogenerate -m "$(m)"

test:
	.venv/bin/python -m pytest tests/ -v

coverage:
	@$(BIN) pytest tests/ --cov-config=pyproject.toml --cov=app --cov-report=term-missing -v

test-no-cov:
	.venv/bin/python -m pytest tests/ -v --no-cov

format:
	@$(BIN) isort --profile black --line-length=100 --skip .venv --skip htmlcov .
	@$(BIN) black --line-length=100 --target-version=py38 --exclude .venv .

lint:
	@$(BIN) isort --profile black --line-length=100 --skip .venv --skip htmlcov --check-only .
	@$(BIN) black --line-length=100 --target-version=py38 --exclude .venv --check .

shell:
	docker compose exec api sh

clean:
	find . -type d -name "__pycache__" -not -path "./.venv/*" | xargs rm -rf
	find . -name "*.pyc" -not -path "./.venv/*" -delete
	@echo "Cleaned."
