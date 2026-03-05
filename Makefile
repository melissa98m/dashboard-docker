.PHONY: build up up-build down restart ps dev dev-build logs lint lint-ci format format-check test test-api test-web test-ci test-e2e shell-api shell-web migrate purge-audit create-user unlock-user db-backup clean health-check

ROLE ?= viewer

build:
	docker compose build

up:
	docker compose up -d

up-build:
	docker compose up -d --build

down:
	docker compose down

restart: down up

ps:
	docker compose ps

dev:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

dev-build:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build

logs:
	docker compose logs -f --tail=200

lint:
	docker compose exec dashboard-api ruff check . && docker compose exec dashboard-api mypy .
	docker compose exec dashboard-web npm run lint

format:
	docker compose exec dashboard-api ruff format .
	docker compose exec dashboard-web npm run format

format-check:
	docker compose run --no-deps --rm -v "$$(pwd)/dashboard-api:/app" dashboard-api ruff format --check .
	docker compose run --no-deps --rm dashboard-web npm run format:check

lint-ci:
	docker compose run --no-deps --rm -v "$$(pwd)/dashboard-api:/app" dashboard-api ruff check . && docker compose run --no-deps --rm -v "$$(pwd)/dashboard-api:/app" dashboard-api mypy .
	docker compose run --no-deps --rm dashboard-web npm run lint

test: test-api test-web

test-api:
	docker compose run --no-deps --rm dashboard-api pytest -v

test-web:
	docker compose run --no-deps --rm -v "$$(pwd)/dashboard-web:/app" -w /app dashboard-web npm run test

test-ci: test-api-ci test-web-ci

test-api-ci:
	docker compose run --no-deps --rm -v "$$(pwd)/dashboard-api:/app" dashboard-api pytest -v -x --tb=short -q

test-web-ci:
	docker compose run --no-deps --rm dashboard-web npm run test

test-e2e:
	@echo "Starting stack for E2E (API + web) ..."
	docker compose up -d dashboard-api dashboard-web
	docker compose exec -T dashboard-api python -c "from app.config import settings; from app.db.auth import create_user, ensure_bootstrap_admin, list_users, reset_user_lockout, update_user_password; username=(settings.auth_bootstrap_admin_username or 'admin').strip() or 'admin'; password=(settings.auth_bootstrap_admin_password or 'AdminPass1234'); ensure_bootstrap_admin(); rows=list_users(query=username, limit=50, offset=0); exact=[row for row in rows if str(row.get('username'))==username]; user_id=int(exact[0]['id']) if exact else int(create_user(username=username, password=password, role='admin')['id']); update_user_password(user_id=user_id, password=password); reset_user_lockout(username=username); print('e2e_user_ready', username)"
	docker compose --profile e2e run --rm dashboard-e2e

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

unlock-user:
	docker compose exec dashboard-api python -m app.cli unlock-user --username "$(USERNAME)"

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
