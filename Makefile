DOCKER_HELPER_DIR := $(if $(wildcard .docker-anonymous/docker-credential-osxkeychain),$(CURDIR)/.docker-anonymous:,)
COMPOSE ?= env PATH="$(DOCKER_HELPER_DIR)$(PATH)" docker compose
INTEGRATION_PROJECT ?= scu-rag-integration
INTEGRATION_PORTS := POSTGRES_PORT=55432 MINIO_API_PORT=59000 MINIO_CONSOLE_PORT=59001 BACKEND_PORT=58000

.PHONY: compose-up compose-down compose-logs compose-status import-dry-run import-publish presentation-update test test-unit test-integration test-smoke integration-test compose-reset

compose-up:
	$(COMPOSE) --env-file .env.compose up --build -d

compose-down:
	$(COMPOSE) --env-file .env.compose down

compose-logs:
	$(COMPOSE) --env-file .env.compose logs -f backend

compose-status:
	curl -fsS http://127.0.0.1:8000/api/status

import-dry-run:
	$(COMPOSE) --env-file .env.compose exec backend python -m backend.scripts.import_legacy_data --dry-run

import-publish:
	$(COMPOSE) --env-file .env.compose exec backend python -m backend.scripts.import_legacy_data --publish

presentation-update:
	python3 scripts/update_presentation.py

test-unit:
	python3 -m unittest discover -s tests/unit -v

test-integration:
	@set -eu; \
	trap '$(INTEGRATION_PORTS) $(COMPOSE) -p $(INTEGRATION_PROJECT) --env-file .env.compose -f docker-compose.yml -f docker-compose.integration.yml down --volumes --remove-orphans' EXIT; \
	$(INTEGRATION_PORTS) $(COMPOSE) -p $(INTEGRATION_PROJECT) --env-file .env.compose -f docker-compose.yml -f docker-compose.integration.yml up --build -d; \
	$(INTEGRATION_PORTS) $(COMPOSE) -p $(INTEGRATION_PROJECT) --env-file .env.compose -f docker-compose.yml -f docker-compose.integration.yml exec -e RUN_COMPOSE_INTEGRATION=1 backend python -m unittest -v tests.integration.test_compose

integration-test: test-integration

test-smoke:
	python3 scripts/smoke_rag.py

test: test-unit
	cd frontend && npm run lint && npm run build

compose-reset:
	$(COMPOSE) --env-file .env.compose down --volumes --remove-orphans
