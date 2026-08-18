MAKEFLAGS += --no-print-directory
PYTHON := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := PYTHONPATH=src $(PYTHON) -m pytest
START_VERBOSE := $(if $(filter --verbose,$(MAKECMDGOALS)),1,0)

# Detección automática de Docker Compose (v1 o v2)
DOCKER_COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

# Variables del cliente
OUTPUT_DIR ?= output
SERVER_HOST ?= 127.0.0.1
SERVER_PORT ?= 5678
BATCH_SIZE ?= 10000
SCALE ?= 2

# Datasets por defecto para tests end-to-end
TEST_TX ?= trans_sample
TEST_ACC ?= LI-Small_accounts
TEST_SOL ?= sample
export TEST_TX TEST_ACC TEST_SOL

# Variables del gateway
MOM_HOST ?= localhost
INPUT_QUEUE ?= input_queue
OUTPUT_QUEUE ?= output_queue

.PHONY: help venv install test test-worker-base clean free-ports client run-clients test-server gateway start down docker-logs iterar solucionar generar log generar-sample caos test-todos test-etapa test-cliente test-gateway test-gateway-resultados test-persistencia test-crash-flush test-caos-secuencial test-crash-watchdog-hooks

help:
	@echo "Targets disponibles:"
	@echo "  make venv                        - Crea el entorno virtual .venv"
	@echo "  make install                     - Instala las dependencias en .venv"
	@echo "  make clean                       - Limpia caches, temporales y libera puertos"
	@echo "  make start                       - Levanta docker-compose en segundo plano (detached)"
	@echo "  make start --verbose             - Levanta docker-compose con logs en consola"
	@echo "  make down                        - Detiene docker-compose"
	@echo "  make log <servicio>              - Muestra logs de un servicio específico"
	@echo "  make client <trans> <cuentas>    - Corre un cliente enviando transacciones y cuentas"
	@echo "  make test-secuencial [cant_cli]  - Corre N clientes de forma secuencial y compara resultados"
	@echo "  make tirar-nodos [segundos]      - Lanza Chaos Monkey aleatorio independiente"
	@echo "  make tirar-nodos [seg] todos     - Matar todos los workers en loop continuo cada [seg]"
	@echo "  make tirar-nodos [seg] etapa     - Matar una etapa al azar en loop continuo cada [seg]"
	@echo "  make tirar-nodos [seg] etapa <p> - Matar etapa específica <p> en loop continuo cada [seg]"
	@echo ""
	@echo "=== CATEGORÍAS DE TESTING ==="
	@echo "  make test-unitarios              - Corre los tests unitarios y de persistencia"
	@echo "  make test-caos-todos [cant_cli]  - Test de caída de todos los workers en simultáneo con clientes"
	@echo "  make test-caos-aleatorio [seg] [cant_cli] - Test de caída continua aleatoria de workers"
	@echo "  make test-caos-secuencial [seg] [cant_cli] - Igual que aleatorio pero clientes secuenciales"
	@echo "  make test-caos-etapa <pref> [cant_cli]  - Test de caída de una etapa específica"
	@echo "  make test-caos-cliente [cant_cli] - Test de caída de un cliente a mitad de envío"
	@echo "  make test-caos-gateway [cant_cli] - Test de caída del gateway"
	@echo "  make test-caos-gateway-resultados- Test de caída del gateway con resultados parciales"
	@echo "  make test-crash-flush [etapa]    - Test del Caso 8 (crash post-flush / pre-barrera)"
	@echo "  make test-crash-caso6 [cant_cli] - Test del Caso 6 (pre-confirmación)"
	@echo "  make test-crash-caso7 [cant_cli] - Test del Caso 7 (pre-barrera)"
	@echo "  make test-crash-leader [cant_cli]- Test de Caída del Líder en Elección"
	@echo "  make test-crash-watchdog-hooks   - Tests de crash hooks del watchdog (topología, detección, elección)"
	@echo "  make test-stress-caos [iter] [cant_cli] - Stress test de caídas masivas en bucle"
	@echo "  make test-stress-crash [iter]    - Stress test de casos de frontera en bucle"
	@echo "  make test-todos                  - Corre toda la suite del sistema (unitarios + crash + caos)"

venv:
	python3 -m venv .venv

install:
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

test:
	./scripts/run_local_tests.sh

test-worker-base:
	$(PYTEST) test/common/worker_base/test_worker_base.py -q

clean:
	-@$(MAKE) free-ports
	-@$(MAKE) down
	-$(DOCKER_COMPOSE) down -v --remove-orphans 2>/dev/null || true
	rm -rf .pytest_cache
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	-docker rm -f $$(docker ps -a -q --filter "name=client_") 2>/dev/null || true
	rm -f /tmp/client_output.txt
	rm -f logs/*.txt
	rm -f logs/*.log
	find output/ -mindepth 1 ! -name '.gitkeep' -delete 2>/dev/null || true
	@if [ -d volume ]; then \
		docker run --rm -v "$$(pwd)/volume:/vol" alpine sh -c "rm -rf /vol/* && chmod -R 777 /vol" 2>/dev/null || true; \
	fi

free-ports:
	@echo "=== Liberando puerto $(SERVER_PORT) (Gateway) ==="
	@if command -v fuser >/dev/null 2>&1; then \
		fuser -k $(SERVER_PORT)/tcp >/dev/null 2>&1 || true; \
	fi
	@echo "=== Liberando puertos de RabbitMQ ==="
	@if command -v fuser >/dev/null 2>&1; then \
		fuser -k 5672/tcp >/dev/null 2>&1 || true; \
		fuser -k 15672/tcp >/dev/null 2>&1 || true; \
	fi

test-server:
	PYTHONPATH=src $(PYTHON) scripts/test_server.py

client:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	TX=$$(echo $$ARGS | cut -d' ' -f1); \
	ACC=$$(echo $$ARGS | cut -d' ' -f2); \
	OUT=$$(echo $$ARGS | cut -d' ' -f3); \
	TX_FILE=$${TRANSACTIONS_FILE:-$$TX}; \
	ACC_FILE=$${ACCOUNTS_FILE:-$$ACC}; \
	OUT_DIR=$${OUTPUT_DIR:-$${OUT:-$(OUTPUT_DIR)}}; \
	CLIENT_SUFFIX=$$(date +%s%N); \
	mkdir -p "$$OUT_DIR" && \
	docker build -q -t client-image -f src/client/Dockerfile src >/dev/null 2>&1 && \
	docker run --rm \
		--name client_$$CLIENT_SUFFIX \
		--network host \
		--user "$$(id -u):$$(id -g)" \
		-v "$(shell pwd)/datasets:/app/datasets" \
		-v "$(shell pwd)/$$OUT_DIR:/app/$$OUT_DIR" \
		-v "$(shell pwd)/logs:/app/logs" \
		-e LOG_FILE="/app/logs/client_$$CLIENT_SUFFIX.txt" \
		-e OUTPUT_APPEND_HOSTNAME="false" \
		-e CLIENT_ID_SUFFIX="$$CLIENT_ID_SUFFIX" \
		-e TRANSACTIONS_FILE="$$TX_FILE" \
		-e ACCOUNTS_FILE="$$ACC_FILE" \
		-e OUTPUT_DIR="$$OUT_DIR" \
		-e SERVER_HOST="$(SERVER_HOST)" \
		-e SERVER_PORT="$(SERVER_PORT)" \
		-e BATCH_SIZE="$(BATCH_SIZE)" \
		client-image


run-clients:
	$(DOCKER_COMPOSE) --profile clients up --build --scale client=$(SCALE)

gateway:
	@if command -v fuser >/dev/null 2>&1; then fuser -k $(SERVER_PORT)/tcp >/dev/null 2>&1 || true; fi
	SERVER_HOST=$(SERVER_HOST) \
	SERVER_PORT=$(SERVER_PORT) \
	MOM_HOST=$(MOM_HOST) \
	INPUT_QUEUE=$(INPUT_QUEUE) \
	OUTPUT_QUEUE=$(OUTPUT_QUEUE) \
	PYTHONPATH=src $(PYTHON) src/gateway/gateway.py

start:
	@mkdir -p logs
	@if [ "$(START_VERBOSE)" = "1" ]; then \
		$(DOCKER_COMPOSE) up --build; \
	else \
		$(DOCKER_COMPOSE) up -d --build > logs/run_start_env.log 2>&1; \
	fi

down:
	@mkdir -p logs
	-@docker rm -f $$(docker ps -a -q --filter "name=client_") 2>/dev/null || true
	@$(DOCKER_COMPOSE) down > logs/run_clean_full.log 2>&1 || true

caos:
	@mkdir -p logs
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_caos_continuo.sh $$ARGS

generar:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$ARGS" ]; then \
		echo "Error: Debes especificar las queries a generar."; \
		echo "Uso: make generar <numeros>"; \
		echo "Ejemplo: make generar 1 2 5"; \
		exit 1; \
	else \
		python3 generar_compose.py $$ARGS; \
	fi

log:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "Error: Debes especificar el nombre del servicio."; \
		echo "Ejemplo: make log gateway"; \
		exit 1; \
	fi
	$(DOCKER_COMPOSE) logs -f $(filter-out $@,$(MAKECMDGOALS))

iterar:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$ARGS" ]; then \
		echo "Error: Debes especificar al menos el número de iteraciones."; \
		echo "Uso: make iterar [iteraciones] [transacciones] [cuentas] [soluciones]"; \
		echo "Ejemplo: make iterar 5 HI-Large_Trans_sample_30 HI-Large_accounts Hi-Large-30"; \
		exit 1; \
	else \
		PYTHONPATH=src $(PYTHON) scripts/utils/iterar_queries.py $$ARGS; \
	fi

solucionar:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$ARGS" ]; then \
		echo "Error: Debes especificar al menos el dataset de transacciones y el de cuentas."; \
		echo "Uso: make solucionar <dataset_transacciones> <dataset_cuentas> [dir_carpeta_solutions]"; \
		echo "Ejemplo: make solucionar HI-Large_Trans_sample_30 HI-Large_accounts Hi-Large-30"; \
		exit 1; \
	else \
		$(PYTHON) scripts/utils/ejecutar_solucion_notebook.py $$ARGS; \
	fi



generar-sample:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	DB=$$(echo $$ARGS | cut -d' ' -f1); \
	PCT=$$(echo $$ARGS | cut -d' ' -f2); \
	PCT=$${PCT:-30}; \
	if [ -z "$$DB" ]; then \
		echo "Error: Debes especificar el nombre del dataset."; \
		echo "Uso: make generar-sample <dataset> [porcentaje]"; \
		echo "Ejemplo: make generar-sample HI-Large_Trans 30"; \
		exit 1; \
	fi; \
	$(PYTHON) scripts/utils/sample_dataset.py \
		--input datasets/$$DB.csv \
		--output datasets/$${DB}_sample_$${PCT}.csv \
		--percentage $$PCT

# --- UNIT TESTS ---
test-unitarios:
	./scripts/tests/run_local_tests.sh

# --- CAOS / FALLAS END-TO-END ---
test-caos-todos:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_todos.sh $$ARGS

test-caos-aleatorio:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_caos_continuo.sh $$ARGS

test-caos-secuencial:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	SEQUENTIAL=1 SEQUENTIAL_SOL="$${TEST_SOL:-sample}" bash scripts/tests/test_caos_continuo.sh $$ARGS

test-secuencial:
	@CANT="$(filter-out $@,$(MAKECMDGOALS))"; \
	CANT=$${CANT:-5}; \
	SEQUENTIAL=1 SEQUENTIAL_SOL="$(TEST_SOL)" CANT="$$CANT" bash -c 'source scripts/tests/test_helpers.sh && lanzar_clientes "$$CANT" $(TEST_TX) $(TEST_ACC)'


tirar-nodos:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$ARGS" ]; then \
		python3 scripts/chaos/chaos_monkey.py 10; \
	else \
		CMD_ARGS=""; \
		FOR_PY=""; \
		for arg in $$ARGS; do \
			if [ "$$arg" = "todos" ]; then \
				FOR_PY="$$FOR_PY --todos"; \
			elif [ "$$arg" = "etapa" ]; then \
				FOR_PY="$$FOR_PY --etapa"; \
			else \
				FOR_PY="$$FOR_PY $$arg"; \
			fi; \
		done; \
		python3 scripts/chaos/chaos_monkey.py $$FOR_PY; \
	fi

test-caos-etapa:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	if [ -z "$$ARGS" ]; then \
		echo "Error: Debes especificar el prefix de la etapa."; \
		echo "Uso: make test-caos-etapa <prefix> [cant_clientes] [tx] [acc] [soluciones] [espera|random]"; \
		exit 1; \
	fi; \
	bash scripts/tests/test_etapa.sh $$ARGS

test-caos-cliente:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_cliente.sh $$ARGS

test-caos-gateway:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_gateway.sh $$ARGS

test-caos-gateway-resultados:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_gateway_resultados.sh $$ARGS

# --- CASOS DE FRONTERA / CRITICAL CORNER CASES ---
test-crash-flush:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_flush.sh $$ARGS

test-crash-caso6:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_caso6.sh $$ARGS

test-crash-caso7:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_caso7.sh $$ARGS

test-crash-leader:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_leader.sh $$ARGS

test-crash-gateway-hooks:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_gateway_hooks.sh $$ARGS

test-crash-watchdog-hooks:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_crash_watchdog_hooks.sh $$ARGS

# --- STRESS TESTING (BUCLES) ---
test-stress-caos:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_stress_todos.sh $$ARGS

test-stress-crash:
	@ARGS="$(filter-out $@,$(MAKECMDGOALS))"; \
	bash scripts/tests/test_stress_crash.sh $$ARGS


# Helpers internos para test-todos (silencian docker y guardan logs en logs/run_*.log)
_kill_zombies = docker rm -f $$(docker ps -a -q --filter "name=client_") 2>/dev/null; true
_full_clean = { $(_kill_zombies); $(DOCKER_COMPOSE) down -v --remove-orphans; \
	docker run --rm -v "$$(pwd)/volume:/vol" -v "$$(pwd)/output:/out" -v "$$(pwd)/logs:/lg" \
		alpine sh -c "rm -rf /vol/* /out/*/ /out/client_id*.txt /lg/*.txt /lg/*.log && chmod -R 777 /vol /out /lg"; } > logs/run_clean_full.log 2>&1
_light_clean = { $(DOCKER_COMPOSE) down -v --remove-orphans; \
	docker run --rm -v "$$(pwd)/volume:/vol" -v "$$(pwd)/output:/out" -v "$$(pwd)/logs:/lg" \
		alpine sh -c "rm -rf /vol/* /out/*/ /out/client_id*.txt /lg/client_*.txt /lg/chaos_monkey_run.log && chmod -R 777 /vol /out /lg"; } > logs/run_clean_light.log 2>&1
_start_env = { $(DOCKER_COMPOSE) up -d --build && \
	ESPERADOS=$$($(DOCKER_COMPOSE) config --services | wc -l); \
	for i in $$(seq 1 60); do \
		CORRIENDO=$$($(DOCKER_COMPOSE) ps --status running --format '{{.Name}}' | wc -l); \
		[ "$$CORRIENDO" -ge "$$ESPERADOS" ] && break; \
		sleep 2; \
	done; } > logs/run_start_env.log 2>&1

# --- TEST TODOS ---
test-todos:
	@$(_full_clean)
	@echo "========================================================="
	@echo "=== 1. Ejecutando tests unitarios y de persistencia ==="
	@echo "========================================================="
	@$(MAKE) test-unitarios
	@echo "========================================================="
	@echo "=== 2. Ejecutando tests de crash hooks del watchdog ==="
	@echo "========================================================="
	@$(MAKE) test-crash-watchdog-hooks 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 3. Ejecutando test de caídas en frío (caso 6) ==="
	@echo "========================================================="
	@$(MAKE) test-crash-caso6 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 4. Ejecutando test de caídas en frío (caso 7) ==="
	@echo "========================================================="
	@$(MAKE) test-crash-caso7 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 5. Ejecutando test de caída de líder de elección ==="
	@echo "========================================================="
	@$(MAKE) test-crash-leader 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 6. Ejecutando test crash flush (caso 8) ==="
	@echo "========================================================="
	@$(_full_clean)
	@$(MAKE) test-crash-flush counter $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 7-13. Ejecutando tests de caos (entorno compartido) ==="
	@echo "========================================================="
	@$(_full_clean)
	@$(_start_env)
	@echo "--- 7. Caos etapa: q2_agregador_shard ---"
	@$(MAKE) test-caos-etapa q2_agregador_shard 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL) 70
	@$(_light_clean)
	@$(_start_env)
	@echo "--- 8. Caos etapa: q4_sumador ---"
	@$(MAKE) test-caos-etapa q4_sumador 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL) 70
	@$(_light_clean)
	@$(_start_env)
	@echo "--- 9. Caos etapa: q3_format_shard ---"
	@$(MAKE) test-caos-etapa q3_format_shard 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL) 70
	@$(_light_clean)
	@$(_start_env)
	@echo "--- 10. Caos cliente ---"
	@$(MAKE) test-caos-cliente 2 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@$(_light_clean)
	@$(_start_env)
	@echo "--- 11. Caos gateway ---"
	@$(MAKE) test-caos-gateway 2 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@$(_light_clean)
	@$(_start_env)
	@echo "--- 12. Caos aleatorio ---"
	@$(MAKE) test-caos-aleatorio 70 2
	@$(_full_clean)
	@$(_start_env)
	@echo "--- 13. Caos total (todos los workers) ---"
	@$(MAKE) test-caos-todos 2 $(TEST_TX) $(TEST_ACC) $(TEST_SOL) 75
	@echo "========================================================="
	@echo "=== 14. Ejecutando tests de crash del gateway (hooks) ==="
	@echo "========================================================="
	@$(MAKE) test-crash-gateway-hooks 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 15. Ejecutando test caos gateway con resultados ==="
	@echo "========================================================="
	@$(MAKE) test-caos-gateway-resultados $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 16. Ejecutando stress test crash (2 iteraciones) ==="
	@echo "========================================================="
	@$(MAKE) test-stress-crash 2 1 $(TEST_TX) $(TEST_ACC) $(TEST_SOL)
	@echo "========================================================="
	@echo "=== 17. Ejecutando stress test caos (2 iteraciones) ==="
	@echo "========================================================="
	@$(_light_clean)
	@$(MAKE) test-stress-caos 2 2 $(TEST_TX) $(TEST_ACC) $(TEST_SOL) 70
	@echo "========================================================="
	@echo "  Todos los tests del sistema pasaron exitosamente"
	@echo "========================================================="

# Ignorar argumentos pasados a targets dinámicos
%:
	@: