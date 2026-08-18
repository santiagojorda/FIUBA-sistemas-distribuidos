#!/usr/bin/env bash
# scripts/test_kill_cliente.sh
set -e
source scripts/tests/test_helpers.sh

CANT_CLIENTES=${1:-3}
TX=${2:-${TEST_TX:-trans_sample}}
ACC=${3:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${4:-${TEST_SOL:-sample}}
ESPERA_ANTES_DE_MATAR=${5:-3}

preparar_entorno

lanzar_clientes "$CANT_CLIENTES" "$TX" "$ACC"

echo "=== Esperando ${ESPERA_ANTES_DE_MATAR}s antes de matar un cliente ==="
sleep "$ESPERA_ANTES_DE_MATAR"

CLIENTE_A_MATAR=$(docker ps --format '{{.Names}}' | grep -E '^client_' | head -n1 || true)
if [ -z "$CLIENTE_A_MATAR" ]; then
    echo "No se encontró ningún contenedor client_* corriendo (¿ya terminó?)"
else
    echo "=== Matando $CLIENTE_A_MATAR ==="
    docker kill "$CLIENTE_A_MATAR"
fi

# Esperamos a los demás (el muerto ya no está en PIDS de wait, pero su `make client`
# va a devolver error; lo ignoramos)
for pid in "${PIDS[@]}"; do
    wait "$pid" || true
done

# Borrar output de clientes que no completaron (el matado) para no comparar basura
for dir in output/*/; do
    [ -d "$dir" ] || continue
    total_csvs=$(find "$dir" -maxdepth 1 -name 'q*_solucion.csv' 2>/dev/null | wc -l)
    if [ "$total_csvs" -lt 5 ]; then
        echo "=== Descartando cliente incompleto $(basename "$dir") ($total_csvs/5 queries) ==="
        rm -rf "$dir"
    fi
done

echo "=== Verificando que el sistema sigue sano para los clientes restantes ==="
comparar_resultados "$SOLUCIONES"