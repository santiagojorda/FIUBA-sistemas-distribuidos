#!/usr/bin/env python3
import argparse
import random
import sys
from pathlib import Path

DEFAULT_INPUT_DATASET = "datasets/trans_sample.csv"
DEFAULT_OUTPUT_DATASET = "datasets/trans_sample.csv"

def sample_dataset(input_path: Path, output_path: Path, percentage: float, method: str, seed: int = 42) -> None:
    if not input_path.exists():
        print(f"Error: El archivo de entrada {input_path} no existe.", file=sys.stderr)
        sys.exit(1)
        
    print(f"Leyendo de: {input_path}")
    print(f"Escribiendo en: {output_path}")
    print(f"Porcentaje: {percentage}%")
    print(f"Método: {method}")
    
    random.seed(seed)
    prob = percentage / 100.0

    total_lines = None
    target_lines = None
    if method == "first":
        print("Contando líneas totales para el método 'first' (esto puede tardar)...")
        with open(input_path, "r", encoding="utf-8") as f:
            total_lines = sum(1 for _ in f) - 1
        target_lines = int(total_lines * prob)
        print(f"Líneas de datos totales: {total_lines}, Objetivo: {target_lines}")

    with open(input_path, "r", encoding="utf-8") as f_in, open(output_path, "w", encoding="utf-8") as f_out:
        header = f_in.readline()
        if not header:
            print("Error: El archivo de entrada está vacío.", file=sys.stderr)
            sys.exit(1)
        f_out.write(header)
        
        written_count = 0
        total_processed = 0
        
        for line in f_in:
            total_processed += 1
            if method == "random":
                if random.random() < prob:
                    f_out.write(line)
                    written_count += 1
            elif method == "uniform":
                if (total_processed * percentage) // 100 > ((total_processed - 1) * percentage) // 100:
                    f_out.write(line)
                    written_count += 1
            elif method == "first":
                if written_count < target_lines:
                    f_out.write(line)
                    written_count += 1
                else:
                    break
            
            if total_processed % 10_000_000 == 0:
                print(f"Procesadas {total_processed} líneas... Escritas {written_count}")

    print(f"¡Listo! Procesadas: {total_processed} líneas de datos. Escritas: {written_count} líneas.")

def main():
    parser = argparse.ArgumentParser(description="Toma una muestra del N% de las líneas de un dataset CSV de transacciones.")
    parser.add_argument("--input", default=DEFAULT_INPUT_DATASET, help="Ruta al dataset CSV de entrada.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_DATASET, help="Ruta al CSV de salida.")
    parser.add_argument("--percentage", type=float, default=30.0, help="Porcentaje de líneas a tomar (default: 30.0).")
    parser.add_argument("--method", choices=["uniform", "random", "first"], default="uniform", 
                        help="Método de muestreo: 'uniform' (distribuido uniformemente, recomendado), 'random' (aleatorio con semilla fija), 'first' (primeras N líneas).")
    parser.add_argument("--seed", type=int, default=42, help="Semilla para el generador aleatorio (solo método 'random').")
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    sample_dataset(input_path, output_path, args.percentage, args.method, args.seed)

if __name__ == "__main__":
    main()
