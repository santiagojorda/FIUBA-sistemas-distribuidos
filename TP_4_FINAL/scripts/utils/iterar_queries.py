#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path

CANTIDAD_EJECUCIONES = 1
ACTUAL_TEMPLATE = "output/q{q}_solucion.csv"
EXPECTED_TEMPLATE = "solutions/small/q{q}_solucion.csv"

TRANSACTIONS_FILE = "datasets/HI-Large_Trans_sample_30.csv"
ACCOUNTS_FILE = "datasets/HI-Large_accounts.csv"


def main():
    project_root = Path(__file__).resolve().parents[1]
    
    scripts_dir = Path(__file__).resolve().parent
    sys.path.append(str(scripts_dir))
    
    try:
        from obtener_queries import obtener_queries_desde_compose
        from comparar_datasets import comparar_csv_sin_orden
        from titular import imprimir_titulo
    except ImportError as e:
        print(f"Error al importar módulos auxiliares desde scripts/: {e}")
        sys.exit(1)
        
    try:
        queries = obtener_queries_desde_compose(project_root / "docker-compose.yml")
    except Exception as e:
        print(f"No se pudo detectar queries del compose. Usando fallback [1, 2, 3, 4, 5]. Error: {e}")
        queries = [1, 2, 3, 4, 5]

    fallas_por_query = {q: 0 for q in queries}

    transactions_file = TRANSACTIONS_FILE
    accounts_file = ACCOUNTS_FILE
    cantidad_iteraciones = CANTIDAD_EJECUCIONES
    expected_template = EXPECTED_TEMPLATE
    args = sys.argv[1:]
    
    if len(args) > 0:
        try:
            cantidad_iteraciones = int(args[0])
        except ValueError:
            print(f"Argumento de iteraciones inválido '{args[0]}', se usará el valor por defecto de {CANTIDAD_EJECUCIONES} iteraciones.")
    if len(args) > 1:
        tx_arg = args[1]
        if not tx_arg.endswith('.csv'):
            tx_arg = f"{tx_arg}.csv"
        transactions_file = tx_arg if ('/' in tx_arg or '\\' in tx_arg) else f"datasets/{tx_arg}"
    if len(args) > 2:
        acc_arg = args[2]
        if not acc_arg.endswith('.csv'):
            acc_arg = f"{acc_arg}.csv"
        accounts_file = acc_arg if ('/' in acc_arg or '\\' in acc_arg) else f"datasets/{acc_arg}"
    if len(args) > 3:
        expected_template = f"solutions/{args[3]}/q{{q}}_solucion.csv"

    output_base = project_root / "output"
    output_base.mkdir(exist_ok=True)
    directorio_anterior = None

    pid = os.getpid()

    for indice in range(1, cantidad_iteraciones + 1):
        imprimir_titulo(f"Iteración {indice}/{cantidad_iteraciones}")

        if directorio_anterior:
            os.system(f"rm -rf '{directorio_anterior}' 2>/dev/null")

        # Directorio aislado por PID e iteración para evitar interferencia con otras instancias paralelas
        run_dir = output_base / f"run_{pid}_{indice}"
        run_dir.mkdir(exist_ok=True)
        run_output_dir = f"output/run_{pid}_{indice}"

        try:
            subprocess.run(
                [
                    "make",
                    "-C", str(project_root),
                    "client",
                    f"TRANSACTIONS_FILE={transactions_file}",
                    f"ACCOUNTS_FILE={accounts_file}",
                    f"OUTPUT_DIR={run_output_dir}"
                ],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"\n[ERROR] El cliente falló con código de salida {e.returncode} en la iteración {indice}.")
            for query in queries:
                fallas_por_query[query] += 1
            os.system(f"rm -rf '{run_dir}' 2>/dev/null")
            continue

        subdirs = [d for d in run_dir.iterdir() if d.is_dir()]
        if subdirs:
            client_output_dir = max(subdirs, key=lambda d: d.stat().st_mtime)
        else:
            client_output_dir = run_dir
        directorio_anterior = run_dir

        for query in queries:
            actual_csv = client_output_dir / f"q{query}_solucion.csv"
            expected_csv = project_root / expected_template.format(q=query)

            son_iguales, mensaje = comparar_csv_sin_orden(actual_csv, expected_csv)
            if son_iguales:
                print(f"\nComparando CSVs para Query {query}: Iguales")
            else:
                fallas_por_query[query] += 1
                print(f"\nComparando CSVs para Query {query}: Diferentes")
                print(mensaje)
                print("\n[ERROR CRÍTICO] Discrepancia detectada en Query {}. Abortando para preservar logs y estado del sistema.".format(query))
                sys.exit(1)

    imprimir_titulo("Resumen")
    print(f"\nResumen de fallas por query después de {cantidad_iteraciones} iteraciones:")
    for query, fallas in fallas_por_query.items():
        print(f"Query {query}: {fallas} fallas en {cantidad_iteraciones} ejecuciones")

    total_fallas = sum(fallas_por_query.values())
    if total_fallas > 0:
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
