SHELL := /bin/bash
PWD := $(shell pwd)

up:
	COMPOSE_HTTP_TIMEOUT=300 docker compose -f docker-compose.yaml up --build --remove-orphans --detach
	docker compose -f docker-compose.yaml logs --follow go-tests
.PHONY: up

local:
	echo "$(PWD)"
	RABBITMQ_PORT=5672 RABBITMQ_HOST=localhost API_PORT=15672 go test ./... -v -count=1
.PHONY: local

down:
	docker compose -f docker-compose.yaml stop -t 1
	docker compose -f docker-compose.yaml down
.PHONY: down

logs:
	docker compose -f docker-compose.yaml logs
.PHONY: logs