#!/usr/bin/env bash
set -e
source scripts/tests/test_helpers.sh

CANT_CLIENTES=${1:-1}
TX=${2:-${TEST_TX:-trans_sample}}
ACC=${3:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${4:-${TEST_SOL:-sample}}

echo "=== Preparando entorno para Test Caso 7 (Crash tras EOFs, pre-disparo de barrera) ==="
make down
timeout 10s docker run --rm -v "$(pwd)/volume:/cleanup" alpine sh -c "rm -rf /cleanup/*" 2>/dev/null \
    || rm -rf volume/* 2>/dev/null || true

echo "=== Levantando sistema con inyección de falla ==="
CRASH_PRE_BARRERA=true make start
esperar_sistema_listo

echo "=== Lanzando $CANT_CLIENTES cliente(s) ==="
lanzar_clientes "$CANT_CLIENTES" "$TX" "$ACC"

echo "=== Esperando finalización del cliente ==="
esperar_clientes

echo "=== Comparando resultados contra soluciones de '$SOLUCIONES' ==="
comparar_resultados "$SOLUCIONES"

echo "=== Test Caso 7 Finalizado. Los resultados son consistentes a pesar del crash pre-barrera. ==="
