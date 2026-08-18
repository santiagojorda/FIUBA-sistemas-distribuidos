#!/usr/bin/env bash
set -e

if [[ "$1" =~ ^[0-9]+$ ]]; then
    # El usuario omitió los casos y pasó directamente el número de iteraciones
    CASOS="caso6 caso7 leader"
    ITERACIONES=${1:-10}
    CANT_CLIENTES=${2:-1}
    TX=${3:-${TEST_TX:-trans_sample}}
    ACC=${4:-${TEST_ACC:-LI-Small_accounts}}
    SOLUCIONES=${5:-${TEST_SOL:-sample}}
else
    # El usuario pasó casos específicos ("caso6", "leader", etc.)
    CASOS=${1:-caso6 caso7 leader}
    ITERACIONES=${2:-10}
    CANT_CLIENTES=${3:-1}
    TX=${4:-${TEST_TX:-trans_sample}}
    ACC=${5:-${TEST_ACC:-LI-Small_accounts}}
    SOLUCIONES=${6:-${TEST_SOL:-sample}}
fi

# Reemplaza comas por espacios por si se pasa "caso6, caso7"
CASOS_CLEAN=$(echo "$CASOS" | tr ',' ' ')

echo "========================================================="
echo "=== Iniciando Stress Test: $ITERACIONES iteraciones de $CASOS_CLEAN ==="
echo "========================================================="

for caso in $CASOS_CLEAN; do
    echo "========================================================="
    echo "=== Evaluando $caso ==="
    echo "========================================================="
    for i in $(seq 1 "$ITERACIONES"); do
        echo ""
        echo ">>> ITERACIÓN $i / $ITERACIONES ($caso) <<<"
        
        if ! make test-crash-$caso "$CANT_CLIENTES" "$TX" "$ACC" "$SOLUCIONES"; then
            echo "========================================================="
            echo "❌ ERROR: El test falló en la iteración $i para $caso"
            echo "Revisa los logs para ver qué ocurrió."
            echo "========================================================="
            exit 1
        fi
    done
done

echo "========================================================="
echo "✅ ÉXITO: Se completaron $ITERACIONES iteraciones de $CASOS_CLEAN sin errores."
echo "========================================================="
