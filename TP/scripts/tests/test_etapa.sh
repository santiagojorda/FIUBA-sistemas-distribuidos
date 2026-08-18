#!/usr/bin/env bash
set -e
source scripts/tests/test_helpers.sh

PREFIX=$1
CANT_CLIENTES=${2:-3}
TX=${3:-${TEST_TX:-trans_sample}}
ACC=${4:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${5:-${TEST_SOL:-sample}}
ESPERA_PARAM=${6:-"random"}

if [ -z "$PREFIX" ]; then
    echo "Uso: $0 <prefix_etapa> [cant_clientes] [tx] [acc] [soluciones] [espera|random]"
    exit 1
fi

if [ "$ESPERA_PARAM" = "random" ]; then
    ESPERA_ARG=10
else
    ESPERA_ARG="$ESPERA_PARAM"
fi

preparar_entorno

lanzar_clientes "$CANT_CLIENTES" "$TX" "$ACC"

# Limpiar el log al iniciar este test
> logs/chaos_monkey_run.log

# Usamos el Chaos Monkey unificado para esperar y matar la etapa
python3 scripts/chaos/chaos_monkey.py $ESPERA_ARG --etapa "$PREFIX" >> logs/chaos_monkey_run.log 2>&1 &
CHAOS_PID=$!

trap limpiar_test_global EXIT

esperar_clientes

echo "=== Clientes finalizaron. Deteniendo Chaos Monkey. ==="

comparar_resultados "$SOLUCIONES"
