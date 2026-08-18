#!/usr/bin/env bash

DOCKER_COMPOSE="${DOCKER_COMPOSE:-docker compose}"

preparar_entorno() {
    local clients
    clients=$(docker ps -a -q --filter "name=client_")
    if [ -n "$clients" ]; then
        timeout 10s docker rm -f $clients 2>/dev/null || true
    fi
    timeout 10s docker run --rm -v "$(pwd)/output:/out" -v "$(pwd)/logs:/lg" \
        alpine sh -c "rm -rf /out/*/ /out/client_id*.txt /lg/client_*.txt /lg/client_stdout_*.txt" 2>/dev/null || true
    trap 'jobs -p | xargs -r kill 2>/dev/null; true' EXIT
    local esperados corriendo
    esperados=$($DOCKER_COMPOSE config --services 2>/dev/null | wc -l)
    corriendo=$($DOCKER_COMPOSE ps --status running --format '{{.Name}}' 2>/dev/null | wc -l)
    if [ "$corriendo" -lt "$esperados" ]; then
        echo "=== Sistema incompleto ($corriendo/$esperados). Limpiando y arrancando... ==="
        make down 2>/dev/null || true
        sleep 2
        timeout 10s docker run --rm -v "$(pwd)/volume:/vol" \
            alpine sh -c "rm -rf /vol/*" 2>/dev/null || true
        make start
        esperar_sistema_listo
    else
        echo "=== Sistema listo ($corriendo/$esperados servicios running) ==="
    fi
}

esperar_sistema_listo() {
    local timeout=${1:-120}
    local esperados
    esperados=$($DOCKER_COMPOSE config --services 2>/dev/null | wc -l)
    echo "=== Esperando que $esperados servicios estén running (timeout ${timeout}s) ==="
    local inicio=$SECONDS
    while true; do
        local corriendo
        corriendo=$($DOCKER_COMPOSE ps --status running --format '{{.Name}}' 2>/dev/null | wc -l)
        if [ "$corriendo" -ge "$esperados" ]; then
            echo "=== $corriendo/$esperados servicios running ($(( SECONDS - inicio ))s) ==="
            return 0
        fi
        if [ $(( SECONDS - inicio )) -ge "$timeout" ]; then
            echo "[ERROR] Timeout: solo $corriendo/$esperados servicios running tras ${timeout}s"
            $DOCKER_COMPOSE ps 2>/dev/null
            return 1
        fi
        sleep 2
    done
}

lanzar_clientes() {
    local cant=$1
    local tx=$2
    local acc=$3
    PIDS=()
    timeout 10s docker run --rm -v "$(pwd)/output:/cleanup_out" -v "$(pwd)/logs:/cleanup_logs" \
        alpine sh -c "rm -rf /cleanup_out/*/ /cleanup_out/client_id_*.txt /cleanup_logs/client_stdout_*.txt" 2>/dev/null \
        || { rm -rf output/*/ output/client_id_*.txt 2>/dev/null || true; }
    for i in $(seq 1 "$cant"); do
        if [ "${SEQUENTIAL:-0}" = "1" ]; then
            if [ "$i" -gt 1 ]; then
                echo ""
            fi
            echo "=== Cliente $i/$cant iniciando ==="
            ( export CLIENT_ID_SUFFIX=$i; make client TRANSACTIONS_FILE="$tx" ACCOUNTS_FILE="$acc" OUTPUT_DIR="output" \
                > "logs/client_stdout_$i.txt" 2>&1 )
            if [ -n "${SEQUENTIAL_SOL:-}" ]; then
                if ! comparar_ultimo_cliente "$SEQUENTIAL_SOL"; then
                    echo "=== FALLO en cliente $i/$cant. Abortando. ==="
                    return 1
                fi
            fi
            echo "=== Cliente $i/$cant finalizado exitosamente ==="
        else
            ( export CLIENT_ID_SUFFIX=$i; make client TRANSACTIONS_FILE="$tx" ACCOUNTS_FILE="$acc" OUTPUT_DIR="output" \
                > "logs/client_stdout_$i.txt" 2>&1 ) &
            PIDS+=($!)
        fi
    done
}

esperar_clientes() {
    for pid in "${PIDS[@]}"; do
        wait "$pid" || echo "[WARN] Proceso $pid (cliente) terminó con error. Ver logs/client_stdout_*.txt"
    done
}

obtener_queries() {
    .venv/bin/python -c "
import sys
sys.path.append('scripts/utils')
from obtener_queries import obtener_queries_desde_compose
qs = obtener_queries_desde_compose('docker-compose.yml')
print(' '.join(str(q) for q in qs))
"
}

comparar_ultimo_cliente() {
    local soluciones_dir=$1
    local fallo=0
    local queries
    queries=$(obtener_queries)
    if [ -z "$queries" ]; then
        queries="1 2 3 4 5"
    fi
    local last_dir
    last_dir=$(ls -td output/*/ 2>/dev/null | head -1)
    if [ -z "$last_dir" ]; then
        echo "No se encontró output de cliente"
        return 1
    fi
    local cid
    cid=$(basename "$last_dir")
    for q in $queries; do
        actual="output/$cid/q${q}_solucion.csv"
        expected="solutions/$soluciones_dir/q${q}_solucion.csv"
        if [ -f "$actual" ]; then
            .venv/bin/python -c "
import sys
sys.path.append('scripts/utils')
from comparar_datasets import comparar_csv_sin_orden
ok, msg = comparar_csv_sin_orden('$actual', '$expected')
print(f'[cliente $cid][q$q]', msg)
sys.exit(0 if ok else 1)
" || fallo=1
        else
            echo "[cliente $cid][q$q] FALTA archivo $actual"
            fallo=1
        fi
    done
    return $fallo
}

comparar_resultados() {
    local soluciones_dir=$1
    local fallo=0
    local queries
    queries=$(obtener_queries)
    if [ -z "$queries" ]; then
        echo "No se pudieron determinar las queries desde docker-compose.yml. Usando fallback 1 2 3 4 5."
        queries="1 2 3 4 5"
    fi
    echo "Queries a comparar: $queries"

    for dir in output/*/; do
        cid=$(basename "$dir")
        for q in $queries; do
            actual="output/$cid/q${q}_solucion.csv"
            expected="solutions/$soluciones_dir/q${q}_solucion.csv"
            if [ -f "$actual" ]; then
                .venv/bin/python -c "
import sys
sys.path.append('scripts/utils')
from comparar_datasets import comparar_csv_sin_orden
ok, msg = comparar_csv_sin_orden('$actual', '$expected')
print(f'[cliente $cid][q$q]', msg)
sys.exit(0 if ok else 1)
" || fallo=1
            else
                echo "[cliente $cid][q$q] FALTA archivo $actual"
                fallo=1
            fi
        done
    done
    return $fallo
}

limpiar_test_global() {
    echo "=== Realizando limpieza de emergencia del test... ==="
    if [ -n "${CHAOS_PID:-}" ]; then
        echo "Apagando Chaos Monkey (PID: $CHAOS_PID)..."
        kill "$CHAOS_PID" 2>/dev/null || true
    fi
    if [ -n "${PIDS:-}" ]; then
        echo "Apagando procesos de clientes..."
        for pid in "${PIDS[@]}"; do
            kill "$pid" 2>/dev/null || true
        done
    fi
    echo "Removiendo contenedores cliente docker residuales..."
    local clients
    clients=$(docker ps -a -q --filter "name=client_")
    if [ -n "$clients" ]; then
        timeout 10s docker rm -f $clients 2>/dev/null || true
    fi
}