#!/usr/bin/env bash
set -e
source scripts/tests/test_helpers.sh

SEGUNDOS_CAOS=10
CANT_CLIENTES=3
TX="${TEST_TX:-LI-Small_Trans}"
ACC="${TEST_ACC:-LI-Small_accounts}"
SOL="${TEST_SOL:-small}"

EXTRA_ARGS=""

NUMS=()
while [[ $# -gt 0 ]]; do
    case $1 in
        --todos)
            EXTRA_ARGS="$EXTRA_ARGS --todos"
            shift
            ;;
        --etapa)
            EXTRA_ARGS="$EXTRA_ARGS --etapa $2"
            shift 2
            ;;
        *)
            if [[ "$1" =~ ^[0-9]+$ ]]; then
                NUMS+=("$1")
            else
                EXTRA_ARGS="$EXTRA_ARGS $1"
            fi
            shift
            ;;
    esac
done

if [ ${#NUMS[@]} -ge 1 ]; then
    SEGUNDOS_CAOS=${NUMS[0]}
fi
if [ ${#NUMS[@]} -ge 2 ]; then
    CANT_CLIENTES=${NUMS[1]}
fi

preparar_entorno
docker build -q -t client-image -f src/client/Dockerfile src >/dev/null 2>&1

# Limpiar el log al iniciar este test
> logs/chaos_monkey_run.log

lanzar_clientes "$CANT_CLIENTES" "$TX" "$ACC"

echo "=== Lanzando Chaos Monkey en segundo plano ==="
echo "Segundos: ${SEGUNDOS_CAOS}s | Extra Args: $EXTRA_ARGS"
python3 scripts/chaos/chaos_monkey.py "$SEGUNDOS_CAOS" $EXTRA_ARGS >> logs/chaos_monkey_run.log 2>&1 &
CHAOS_PID=$!
trap limpiar_test_global EXIT

esperar_clientes

echo "=== Clientes finalizaron. Deteniendo Chaos Monkey. ==="

comparar_resultados "$SOL"
