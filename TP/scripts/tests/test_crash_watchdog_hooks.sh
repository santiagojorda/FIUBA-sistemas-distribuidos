#!/usr/bin/env bash
set -e
source scripts/tests/test_helpers.sh

CANT_CLIENTES=${1:-1}
TX=${2:-${TEST_TX:-trans_sample}}
ACC=${3:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${4:-${TEST_SOL:-sample}}

run_hook_test() {
    local NOMBRE="$1"
    local ENV_VAR="$2"
    local DESC="$3"

    echo ""
    echo "--- Watchdog Hook: $NOMBRE ($DESC) ---"
    make down 2>/dev/null || true
    timeout 10s docker run --rm -v "$(pwd)/volume:/cleanup" alpine sh -c "rm -rf /cleanup/*" 2>/dev/null \
        || rm -rf volume/* 2>/dev/null || true

    echo "=== Levantando sistema con $ENV_VAR=true ==="
    eval "$ENV_VAR=true make start"
    esperar_sistema_listo

    echo "=== Lanzando $CANT_CLIENTES cliente(s) ==="
    lanzar_clientes "$CANT_CLIENTES" "$TX" "$ACC"

    echo "=== Esperando finalización del cliente ==="
    esperar_clientes

    echo "=== Comparando resultados ==="
    comparar_resultados "$SOLUCIONES"

    echo "=== $NOMBRE: OK ==="
}

echo "========================================================="
echo "=== Tests de crash hooks del watchdog ==="
echo "========================================================="

run_hook_test "post-topology-save" "CRASH_WD_POST_TOPOLOGY_SAVE" \
    "Crash tras guardar topología — debe recargar de disco al reiniciar"

run_hook_test "post-leader-declare" "CRASH_WD_POST_LEADER_DECLARE" \
    "Crash del líder recién electo — standby debe tomar el liderazgo"

run_hook_test "pre-publish-caida" "CRASH_WD_PRE_PUBLISH_CAIDA" \
    "Crash antes de publicar caída — debe re-detectar tras reinicio"

echo ""
echo "========================================================="
echo "=== Todos los hooks del watchdog pasaron ==="
echo "========================================================="
