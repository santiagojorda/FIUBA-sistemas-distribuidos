#!/usr/bin/env bash
# Suite de tests de tolerancia a fallos del gateway.
# Cada caso inyecta un crash en un punto crítico distinto del pipeline.
#
# Uso:
#   bash scripts/tests/test_crash_gateway_hooks.sh [cant_clientes] [tx] [acc] [soluciones]
#
set -e
source scripts/tests/test_helpers.sh

CANT_CLIENTES=${1:-1}
TX=${2:-${TEST_TX:-trans_sample}}
ACC=${3:-${TEST_ACC:-LI-Small_accounts}}
SOLUCIONES=${4:-${TEST_SOL:-sample}}

CASOS=(
    "CRASH_GATEWAY_UPSTREAM_BEFORE_ACK|Pipeline: crash después de publicar a RabbitMQ, antes de ACK al cliente"
    "CRASH_GATEWAY_DOWNSTREAM_BEFORE_SEND|Pipeline: crash antes de enviar EOF de query al cliente"
    "CRASH_GATEWAY_DOWNSTREAM_BEFORE_ACK|Pipeline: crash después de enviar EOF de query, antes de ACK a RabbitMQ"
    "CRASH_GATEWAY_BEFORE_FINALIZE|Pipeline: crash con todas las queries entregadas, antes de FIN_DE_REGISTROS"
    "CRASH_GATEWAY_BEFORE_PERSIST_CONNECTED|Estado: crash antes de persistir flag conectado"
    "CRASH_GATEWAY_AFTER_PERSIST_CONNECTED|Estado: crash después de persistir flag conectado, antes de enviar datos"
    "CRASH_GATEWAY_BEFORE_PERSIST_DATOS_ENVIADOS|Estado: crash después de EOF a workers, antes de persistir datos_enviados"
    "CRASH_GATEWAY_AFTER_PERSIST_DATOS_ENVIADOS|Estado: crash después de persistir datos_enviados"
    "CRASH_GATEWAY_BEFORE_PERSIST_QUERY|Estado: crash después de confirmar query al cliente, antes de persistir"
    "CRASH_GATEWAY_AFTER_PERSIST_QUERY|Estado: crash después de persistir query entregada"
)

TOTAL=${#CASOS[@]}
PASARON=0

for i in "${!CASOS[@]}"; do
    IFS='|' read -r ENV_VAR DESCRIPCION <<< "${CASOS[$i]}"
    NUM=$((i + 1))

    # Permitir filtrar un caso específico con la variable ONLY_CASE
    if [ -n "$ONLY_CASE" ] && [ "$ONLY_CASE" != "$NUM" ] && [ "$ONLY_CASE" != "$ENV_VAR" ]; then
        continue
    fi

    echo ""
    echo "========================================================="
    echo "=== Caso $NUM/$TOTAL: $DESCRIPCION ==="
    echo "=== (env: $ENV_VAR=true) ==="
    echo "========================================================="

    make down 2>/dev/null || true
    timeout 10s docker run --rm -v "$(pwd)/volume:/vol" -v "$(pwd)/output:/out" -v "$(pwd)/logs:/lg" \
        alpine sh -c "rm -rf /vol/* /out/*/ /out/client_id*.txt /lg/client_*.txt" 2>/dev/null || true

    echo "=== Levantando sistema con inyección de falla ==="
    eval "$ENV_VAR=true make start"
    esperar_sistema_listo

    echo "=== Lanzando $CANT_CLIENTES cliente(s) ==="
    lanzar_clientes "$CANT_CLIENTES" "$TX" "$ACC"

    echo "=== Esperando finalización ==="
    esperar_clientes

    echo "=== Comparando resultados ==="
    if comparar_resultados "$SOLUCIONES"; then
        echo "=== CASO $NUM OK ==="
        PASARON=$((PASARON + 1))
    else
        echo "========================================================="
        echo "FALLO en caso $NUM: $DESCRIPCION"
        echo "========================================================="
        exit 1
    fi
done

echo ""
echo "========================================================="
echo "  $PASARON/$TOTAL casos de gateway pasaron exitosamente"
echo "========================================================="
