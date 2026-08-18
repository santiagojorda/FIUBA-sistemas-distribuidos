#!/usr/bin/env python3
import argparse
import sys
import pandas as pd
from pathlib import Path

DIR1 = "output/mi_prueba/efd678fe-5bd1-441f-a6d3-7b7286caa338"
DIR2 = "solutions/small"

TEMPLATE = "q{q}_solucion.csv"


def comparar_csv_sin_orden(archivo1: Path | str, archivo2: Path | str) -> tuple[bool, str]:
    try:
        df1 = pd.read_csv(archivo1)
        df2 = pd.read_csv(archivo2)

        if set(df1.columns) != set(df2.columns):
            mensaje = (
                "Los archivos NO son iguales: Tienen columnas diferentes.\n"
                f"Columnas CSV 1: {list(df1.columns)}\n"
                f"Columnas CSV 2: {list(df2.columns)}"
            )
            return False, mensaje

        df2 = df2[df1.columns]
        df1_ordenado = df1.sort_values(by=list(df1.columns)).reset_index(drop=True)
        df2_ordenado = df2.sort_values(by=list(df1.columns)).reset_index(drop=True)

        if df1_ordenado.equals(df2_ordenado):
            return True, "¡Los archivos CSV son exactamente IGUALES! (ignorando el orden)"

        return False, "Los archivos NO son iguales: El contenido de las filas difiere."

    except FileNotFoundError as exc:
        return False, f"Error: No se pudo encontrar el archivo: {exc.filename}"
    except Exception as exc:
        return False, f"Ocurrió un error inesperado al leer los archivos: {exc}"


def main():
    parser = argparse.ArgumentParser(description="Compara archivos CSV entre dos directorios usando una plantilla para cada query.")
    parser.add_argument("--dir1", default=DIR1, help="Ruta al primer directorio.")
    parser.add_argument("--dir2", default=DIR2, help="Ruta al segundo directorio.")
    parser.add_argument("--template", default=TEMPLATE, help="Plantilla para el nombre del archivo (debe contener {q}).")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).resolve().parents[1]
    
    scripts_dir = Path(__file__).resolve().parent
    if str(scripts_dir) not in sys.path:
        sys.path.append(str(scripts_dir))
        
    try:
        from obtener_queries import obtener_queries_desde_compose
        queries = obtener_queries_desde_compose(project_root / "docker-compose.yml")
        print(f"Queries detectadas desde el docker-compose: {queries}")
    except Exception as e:
        queries = [1, 2, 3, 4, 5]
        print(f"No se pudieron cargar las queries dinámicamente: {e}. Usando fallback por defecto: {queries}")

    d1 = Path(args.dir1)
    if not d1.is_absolute():
        d1 = project_root / d1
        
    d2 = Path(args.dir2)
    if not d2.is_absolute():
        d2 = project_root / d2

    print(f"Comparando directorios:\n  Dir 1: {d1}\n  Dir 2: {d2}\n  Plantilla: {args.template}\n")
    
    hubo_fallas = False
    for q in queries:
        nombre_archivo = args.template.format(q=q)
        f1 = d1 / nombre_archivo
        f2 = d2 / nombre_archivo
        
        print(f"--- Query {q} ({nombre_archivo}) ---")
        son_iguales, mensaje = comparar_csv_sin_orden(f1, f2)
        print(mensaje)
        if not son_iguales:
            hubo_fallas = True
        print()

    if hubo_fallas:
        print("Resultado General: Se encontraron diferencias o errores en la comparación.")
        sys.exit(1)
    else:
        print("Resultado General: Todos los archivos correspondientes son exactamente IGUALES.")
        sys.exit(0)


if __name__ == "__main__":
    main()
