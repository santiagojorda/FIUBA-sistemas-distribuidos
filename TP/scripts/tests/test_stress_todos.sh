#!/usr/bin/env bash
set -e

ITERACIONES=${1:-20}
CANT_CLIENTES=${2:-2}
TX=${3:-${TEST_TX:-trans_sample}}
ACC=${4:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${5:-${TEST_SOL:-sample}}
ESPERA_ANTES_DE_MATAR=${6:-5}

echo "========================================================="
echo "=== Iniciando Stress Test: $ITERACIONES iteraciones de test_todos ($CANT_CLIENTES clientes) ==="
echo "========================================================="

for i in $(seq 1 "$ITERACIONES"); do
    echo ""
    echo ">>> ITERACIÓN $i / $ITERACIONES <<<"

    if ! bash scripts/tests/test_todos.sh "$CANT_CLIENTES" "$TX" "$ACC" "$SOLUCIONES" "$ESPERA_ANTES_DE_MATAR"; then
        echo "========================================================="
        echo "❌ ERROR: El test falló en la iteración $i"
        echo "Revisa los logs para ver qué ocurrió."
        echo "========================================================="
        exit 1
    fi
done

echo "========================================================="
echo "✅ ÉXITO: Se completaron $ITERACIONES iteraciones sin errores."
echo "========================================================="
