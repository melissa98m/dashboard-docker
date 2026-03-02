.PHONY: build up down restart ps dev logs lint format test test-api test-web shell-api shell-web migrate purge-audit create-user db-backup clean health-check

ROLE ?= viewer

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

restart: down up

ps:
	docker compose ps

dev:
	docker compose up --build

logs:
	docker compose logs -f --tail=200

lint:
	docker compose exec dashboard-api ruff check . && docker compose exec dashboard-api mypy .
	docker compose exec dashboard-web npm run lint

format:
	docker compose exec dashboard-api ruff format .
	docker compose exec dashboard-web npm run format

test: test-api test-web

test-api:
	docker compose run --no-deps --rm dashboard-api pytest -v

test-web:
	docker compose run --no-deps --rm dashboard-web npm run test

shell-api:
	docker compose exec dashboard-api sh

shell-web:
	docker compose exec dashboard-web sh

migrate:
	docker compose exec dashboard-api python -m app.cli migrate

purge-audit:
	docker compose exec dashboard-api python -m app.cli purge-audit

create-user:
	docker compose exec dashboard-api python -m app.cli create-user --username "$(USERNAME)" --role "$(ROLE)"

db-backup:
	@mkdir -p backups
	docker cp dashboard-api:/data/dashboard.db ./backups/dashboard_$$(date +%Y%m%d_%H%M%S).db
	@echo "Backup saved to backups/"

clean:
	docker compose down 2>/dev/null || true
	docker system prune -f
	docker image prune -f

health-check:
	@./scripts/health-check.sh
