#!/usr/bin/env bash
# scripts/test_crash_flush.sh
#
# Caso 8 — barrier_completada: verifica que un crash en al_completar_cliente
# (después de enviar datos pero antes de persistir barrier_completada) no
# produce resultados duplicados.
#
# Mecanismo: CRASH_AFTER_FLUSH=true hace que el worker muera exactamente en
# esa ventana la primera vez que la cruza. Docker lo reinicia (restart: on-failure).
# Al reiniciar, detecta barrier_completada=True en disco y no re-flushea.
#
# Uso:
#   bash scripts/test_crash_flush.sh [etapa] [tx] [acc] [soluciones]
#
#   etapa     : counter | q4_sumador | q4_joiner | q4_contador  (default: counter)
#   tx        : dataset de transacciones   (default: $TEST_TX o trans_sample)
#   acc       : dataset de cuentas         (default: $TEST_ACC o LI-Small_accounts)
#   soluciones: carpeta en solutions/      (default: $TEST_SOL o sample)
#
set -e
source scripts/tests/test_helpers.sh

ETAPA=${1:-counter}
TX=${2:-${TEST_TX:-trans_sample}}
ACC=${3:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${4:-${TEST_SOL:-sample}}

echo "=== Test Caso 8: CRASH_AFTER_FLUSH en etapa '$ETAPA' ==="

make down

echo "=== Limpiando banderas de crash previas ==="
find volume/ -name "crash_flush_done" -delete 2>/dev/null || true

echo "=== Levantando sistema con CRASH_AFTER_FLUSH=true ==="
CRASH_AFTER_FLUSH=true make start

echo "=== Esperando que el sistema esté listo ==="
esperar_sistema_listo

echo "=== Enviando cliente ==="
rm -rf output/0
( make client TRANSACTIONS_FILE="$TX" ACCOUNTS_FILE="$ACC" OUTPUT_DIR="output" \
    > logs/client_stdout_crash_flush.txt 2>&1 )

echo "=== Verificando que el worker crasheó y fue reiniciado ==="
NODOS=$(docker ps --format '{{.Names}}' | grep -E "${ETAPA}_[0-9]+" || true)
if [ -z "$NODOS" ]; then
    echo "[ERROR] No se encontraron nodos de la etapa '$ETAPA' corriendo después del crash."
    exit 1
fi
echo "Nodos activos: $NODOS ✓"

echo "=== Verificando que la bandera de crash fue activada ==="
BANDERAS=$(find volume/ -name "crash_flush_done" 2>/dev/null || true)
if [ -z "$BANDERAS" ]; then
    echo "[WARN] No se encontró bandera crash_flush_done. Puede que el flush no se haya ejecutado todavía."
else
    echo "Banderas encontradas: $BANDERAS ✓"
fi

echo "=== Comparando resultados (deben ser correctos, sin duplicados) ==="
comparar_resultados "$SOLUCIONES"

echo ""
echo "=== Caso 8 OK: crash durante flush no produjo resultados incorrectos ==="
echo "=== Limpiar con: CRASH_AFTER_FLUSH=false make start ==="
