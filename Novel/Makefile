COMPOSE ?= docker compose
COMPOSE_ENV_FILE ?= .env
BASE_URL ?= http://127.0.0.1:18080
COMPOSE_BASE_URL ?= http://127.0.0.1:80
NATIVE_ENV_FILE ?= .env.native
NATIVE_PYTHON ?= .venv/bin/python

.PHONY: build up down logs migrate health smoke test-backend test-backend-integration test-frontend test-cli test \
	native-install native-build native-up native-down native-restart native-status native-logs \
	native-migrate native-provision native-health native-smoke compose-build compose-up compose-down compose-logs \
	compose-migrate compose-health compose-smoke compose-test-backend compose-test-frontend

# Native source execution is the default. Docker remains an optional deployment path.
build: native-build

up: native-up

down: native-down

logs: native-logs

migrate: native-migrate

health: native-health

smoke: native-smoke

native-install:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_install.sh

native-provision:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_provision.sh

native-build: native-install
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_build.sh

native-up: native-build
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_ctl.sh start

native-down:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_ctl.sh stop

native-restart:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_ctl.sh restart

native-status:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_ctl.sh status

native-logs:
	tail -f .run/native/*.log

native-migrate:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" ./scripts/native_migrate.sh

native-health:
	curl -fsS "$(BASE_URL)/api/health"

native-smoke:
	NATIVE_ENV_FILE="$(NATIVE_ENV_FILE)" BASE_URL="$(BASE_URL)" ./scripts/native_smoke.sh

test-backend:
	cd backend && ../$(NATIVE_PYTHON) -m pytest -q

test-backend-integration:
	cd backend && ../$(NATIVE_PYTHON) -m pytest -q -m integration

test-frontend:
	cd frontend && npm test -- --run

test-cli:
	cd cli && ../$(NATIVE_PYTHON) -m pytest -q tests

test: test-backend test-frontend test-cli

# Explicit optional Docker targets. These do not participate in the native path.
compose-build:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" build

compose-up:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" up -d --build

compose-down:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" down

compose-logs:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" logs -f --tail=200

compose-migrate:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" run --rm migrate

compose-health:
	curl -fsS "$(COMPOSE_BASE_URL)/api/health"

compose-smoke:
	BASE_URL="$(COMPOSE_BASE_URL)" ./scripts/compose_smoke.sh

compose-test-backend:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" run --rm --no-deps api pytest -q

compose-test-frontend:
	$(COMPOSE) --env-file "$(COMPOSE_ENV_FILE)" -f compose.yaml -f compose.test.yaml --profile test run --rm frontend-test
