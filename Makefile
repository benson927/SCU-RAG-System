DOCKER_HELPER_DIR := $(if $(wildcard .docker-anonymous/docker-credential-osxkeychain),$(CURDIR)/.docker-anonymous:,)
COMPOSE ?= env PATH="$(DOCKER_HELPER_DIR)$(PATH)" docker compose

.PHONY: compose-up compose-down compose-logs compose-status import-dry-run import-publish integration-test compose-reset

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

integration-test:
	$(COMPOSE) --env-file .env.compose -f docker-compose.yml -f docker-compose.integration.yml up --build -d
	$(COMPOSE) --env-file .env.compose -f docker-compose.yml -f docker-compose.integration.yml exec -e RUN_COMPOSE_INTEGRATION=1 backend python -m unittest -v test_compose_integration.py

compose-reset:
	$(COMPOSE) --env-file .env.compose down --volumes --remove-orphans
