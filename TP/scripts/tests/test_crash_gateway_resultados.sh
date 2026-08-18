#!/usr/bin/env bash
# scripts/test_crash_gateway_resultados.sh
#
# Verifica tolerancia a fallos del gateway cuando cae MIENTRAS el cliente ya
# está recibiendo resultados de al menos una query.
#
# Flujo:
#   1. Se resetean volúmenes de workers y se reinicia el sistema para un estado limpio.
#   2. Se lanza un cliente (nuevo client_id).
#   3. Se espera hasta que el cliente registre la primera query completada.
#   4. Se mata gateway_01.
#   5. El actuador detecta la caída y lo reinicia.
#   6. El cliente reconecta y termina de recibir las queries restantes.
#   7. Se comparan los resultados contra la solución esperada.
#
# Uso:
#   bash scripts/test_crash_gateway_resultados.sh [tx] [acc] [soluciones] [timeout_resultado_s]
#
#   tx               : archivo de transacciones (default: trans_sample)
#   acc              : archivo de cuentas       (default: $TEST_ACC o LI-Small_accounts)
#   soluciones       : carpeta en solutions/    (default: small)
#   timeout_resultado: segundos máx para esperar primer resultado (default: 360)
#
set -e
source scripts/tests/test_helpers.sh

TX=${1:-${TEST_TX:-trans_sample}}
ACC=${2:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${3:-${TEST_SOL:-sample}}
TIMEOUT_RESULTADO=${4:-360}

echo "=== Test: gateway cae mientras el cliente recibe resultados ==="
echo "    dataset:   $TX / $ACC"
echo "    soluciones: solutions/$SOLUCIONES"

# ---------- 0. Entorno limpio ----------
echo "=== Limpiando volúmenes de workers y reiniciando sistema... ==="
make down 2>/dev/null || true
timeout 10s docker run --rm -v "$(pwd)/volume:/vol" alpine sh -c "rm -rf /vol/*" 2>/dev/null || true
# Forzar nuevo client_id para que los workers no reutilicen estado de runs anteriores
rm -f output/client_id.txt 2>/dev/null || true
make start

echo "=== Esperando que el sistema esté listo... ==="
sleep 10

# ---------- 1. Lanzar cliente ----------
lanzar_clientes 1 "$TX" "$ACC"
LOG="logs/client_stdout_1.txt"

# ---------- 2. Esperar primer resultado ----------
echo "=== Esperando que el cliente complete al menos una query (max ${TIMEOUT_RESULTADO}s)... ==="
INICIO=$(date +%s)
while true; do
    AHORA=$(date +%s)
    if [ $((AHORA - INICIO)) -ge "$TIMEOUT_RESULTADO" ]; then
        echo "[ERROR] Timeout: el cliente no recibió ninguna query en ${TIMEOUT_RESULTADO}s"
        exit 1
    fi
    if grep -q "Finalizada" "$LOG" 2>/dev/null; then
        PRIMERA=$(grep "Finalizada" "$LOG" | head -1 | sed 's/.*INFO \[root\] //')
        echo "=== Detectado: $PRIMERA ==="
        break
    fi
    sleep 1
done

# ---------- 3. Matar gateway ----------
echo "=== Matando gateway_01 ==="
docker kill gateway_01 || echo "[WARN] gateway_01 ya no estaba corriendo"

# ---------- 4. Esperar reinicio por el actuador ----------
echo "=== Esperando que el actuador reinicie gateway_01... ==="
MAX_REINICIO=120
REINICIADO=0
for i in $(seq 1 $MAX_REINICIO); do
    if docker ps --format '{{.Names}}' | grep -q "^gateway_01$"; then
        echo "=== gateway_01 volvió a estar corriendo (detectado en ${i}s) ==="
        REINICIADO=1
        break
    fi
    sleep 1
done

if [ "$REINICIADO" -eq 0 ]; then
    echo "[ERROR] El actuador no reinició gateway_01 en ${MAX_REINICIO}s"
    exit 1
fi

# ---------- 5. Esperar cliente ----------
echo "=== Esperando que el cliente complete todas las queries... ==="
esperar_clientes

# ---------- 6. Comparar ----------
echo "=== Comparando resultados ==="
comparar_resultados "$SOLUCIONES"

echo ""
echo "=== OK: el gateway cayó con resultados parciales y el cliente terminó correctamente ==="
