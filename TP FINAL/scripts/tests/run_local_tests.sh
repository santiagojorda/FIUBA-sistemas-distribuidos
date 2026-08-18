#!/bin/bash
set -e

echo "=== Ejecutando todos los tests locales (sin contenedores) ==="

echo ""
echo "1/10 - Worker Base tests..."
PYTHONPATH=src/workers:src .venv/bin/pytest test/common/worker_base/ -q

echo "2/10 - Filter tests..."
PYTHONPATH=src/workers/filtro:src/workers:src .venv/bin/pytest test/common/workers/test_filter.py -q

echo "3/10 - Counter & Persistencia Counter tests..."
PYTHONPATH=src/workers/contador:src/workers:src .venv/bin/pytest test/common/workers/test_add.py test/workers/test_counter_persistencia.py test/workers/test_eof_race_condition.py test/workers/test_barrera_con_caidas.py -q

echo "4/10 - Aggregator & Persistencia Aggregator tests..."
PYTHONPATH=src/workers/contador_distinto:src/workers:src .venv/bin/pytest test/common/workers/test_aggregator.py test/workers/test_contador_distinto_persistencia.py -q

echo "5/10 - Projection tests..."
PYTHONPATH=src/workers/proyeccion:src/workers:src .venv/bin/pytest test/common/workers/test_projection.py -q

echo "6/10 - Bank Shard tests..."
PYTHONPATH=src/workers/bank_shard:src/workers:src .venv/bin/pytest test/workers/test_bank_shard_persistencia.py -q

echo "7/10 - Format Shard tests..."
PYTHONPATH=src/workers/format_shard:src/workers:src .venv/bin/pytest test/workers/test_format_shard_persistencia.py -q

echo "8/10 - Joiner Q4 tests..."
PYTHONPATH=src/workers/joiner_q4:src/workers:src .venv/bin/pytest test/workers/test_joiner_q4_persistencia.py -q

echo "9/10 - Persistencia Base tests..."
PYTHONPATH=src/workers:src .venv/bin/pytest test/common/persistencia/test_persistencia.py -q

echo "10/12 - Watchdog & Ring Election tests..."
PYTHONPATH=src .venv/bin/pytest test/watchdog/ -q

echo "11/12 - Client ACK Starvation tests..."
PYTHONPATH=src/client:src .venv/bin/pytest test/gateway/test_client_ack_starvation.py -q

echo "12/12 - Convertidor & Cotizaciones tests..."
PYTHONPATH=src/workers/convertidor:src/workers:src .venv/bin/pytest test/workers/test_cliente_cotizaciones.py -q

echo ""
echo "========================================================="
echo "  ¡Todos los tests locales pasaron exitosamente!"
echo "========================================================="
