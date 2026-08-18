#!/usr/bin/env python3
"""
Versión Polars de ejecutar_solucion_notebook.py.
Usa scan_csv (lazy) para no cargar todo el CSV en memoria de una vez,
lo que permite procesar datasets grandes sin saturar la RAM.
"""
import sys
import shutil
import polars as pl
import requests
from datetime import date, timedelta
from pathlib import Path

# RUTA_DATASETS = "datasets"
# DATASET_TRANS = "HI-Large_Trans.csv"
# DATASET_ACCOUNTS = "HI-Large_accounts.csv"
# RUTA_SALIDAS = "output/Large"

RUTA_DATASETS = "datasets"
DATASET_TRANS = "trans_sample.csv"
DATASET_ACCOUNTS = "LI-Small_accounts.csv"
RUTA_SALIDAS = "solutions/sample"


def obtener_tasas_cambio():
    CURRENCY_MAP = {
        "US Dollar": "USD", "Euro": "EUR", "UK Pound": "GBP", "Yen": "JPY",
        "Australian Dollar": "AUD", "Brazil Real": "BRL", "Canadian Dollar": "CAD",
        "Mexican Peso": "MXN", "Rupee": "INR", "Shekel": "ILS",
        "Swiss Franc": "CHF", "Yuan": "CNY", "Ruble": "RUB",
        "Saudi Riyal": "SAR", "Bitcoin": "BTC",
    }
    ISO_TO_NAME = {v: k for k, v in CURRENCY_MAP.items()}

    try:
        resp = requests.get("https://api.frankfurter.app/2022-09-01..2022-09-05?base=USD", timeout=10)
        resp.raise_for_status()
        raw = resp.json()["rates"]
    except Exception as e:
        print(f"Error al obtener tasas de cambio desde Frankfurter API: {e}", file=sys.stderr)
        sys.exit(1)

    registros = []
    ultimo = None
    d = date(2022, 9, 1)
    while d <= date(2022, 9, 5):
        iso_key = d.isoformat()
        slash_key = d.strftime("%Y/%m/%d")
        if iso_key in raw:
            ultimo = raw[iso_key]
        if ultimo:
            registros.append({"Date": slash_key, "Payment Currency": "US Dollar", "rate": 1.0})
            for iso, tasa in ultimo.items():
                nombre = ISO_TO_NAME.get(iso)
                if nombre:
                    registros.append({"Date": slash_key, "Payment Currency": nombre, "rate": float(tasa)})
        d += timedelta(days=1)

    return pl.DataFrame(registros)


def parsear_args(args, project_root):
    if len(args) >= 1:
        arg_str = args[0]
        if not arg_str.endswith('.csv'):
            arg_str = f"{arg_str}.csv"
        path_arg = Path(arg_str)
        if path_arg.is_absolute():
            input_trans = path_arg
        elif len(path_arg.parts) == 1:
            input_trans = project_root / RUTA_DATASETS / path_arg
        else:
            input_trans = project_root / path_arg
    else:
        input_trans = project_root / RUTA_DATASETS / DATASET_TRANS

    if len(args) >= 2:
        accounts_arg = args[1]
        if not accounts_arg.endswith('.csv'):
            accounts_arg = f"{accounts_arg}.csv"
        path_accounts_arg = Path(accounts_arg)
        if path_accounts_arg.is_absolute():
            input_accounts = path_accounts_arg
        elif len(path_accounts_arg.parts) == 1:
            input_accounts = project_root / RUTA_DATASETS / path_accounts_arg
        else:
            input_accounts = project_root / path_accounts_arg
    else:
        input_accounts = project_root / RUTA_DATASETS / DATASET_ACCOUNTS

    if len(args) >= 3:
        dir_arg = args[2]
        if '/' not in dir_arg and '\\' not in dir_arg:
            dir_arg = f"solutions/{dir_arg}"
        path_arg = Path(dir_arg)
        out_dir = path_arg if path_arg.is_absolute() else project_root / path_arg
    else:
        out_dir = project_root / RUTA_SALIDAS

    return input_trans, input_accounts, out_dir


def main():
    project_root = Path(__file__).resolve().parents[1]
    input_trans, input_accounts, out_dir = parsear_args(sys.argv[1:], project_root)

    if not input_trans.exists():
        print(f"Error: No existe el archivo de transacciones: {input_trans}", file=sys.stderr)
        sys.exit(1)
    if not input_accounts.exists():
        print(f"Error: No existe el archivo de cuentas: {input_accounts}", file=sys.stderr)
        sys.exit(1)

    if out_dir.exists():
        print(f"Borrando carpeta de destino existente: {out_dir}")
        if out_dir.is_dir():
            shutil.rmtree(out_dir)
        else:
            out_dir.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)

    outputs = {q: out_dir / f"q{q}_solucion.csv" for q in range(1, 6)}

    print("--- Cargando Datasets (lazy con Polars) ---")
    print(f"Transacciones: {input_trans}")
    print(f"Cuentas: {input_accounts}")

    # scan_csv es lazy: construye el plan de ejecución pero no lee el archivo todavía
    trans_lazy = (pl.scan_csv(str(input_trans), infer_schema_length=10000)
        .rename({"Account_duplicated_0": "Account.1"})
    )
    accounts_lazy = pl.scan_csv(str(input_accounts), infer_schema_length=10000)

    # Filtros base reutilizados en varias queries — se materializan una sola vez
    trans_usd = trans_lazy.filter(pl.col("Payment Currency") == "US Dollar")

    print("\nFiltrando transacciones USD y período Sept 1-6...")
    # Materializamos trans_usd_sept_1st porque se usa en Q3, Q4 y dentro de Q4 dos veces
    trans_usd_sept_1st = (trans_usd
        .filter(
            (pl.col("Timestamp") >= "2022/09/01") & (pl.col("Timestamp") <= "2022/09/06")
        )
        .collect()
    )
    print(f"Transacciones USD Sept 1-6: {len(trans_usd_sept_1st)} filas")

    # --- Query 1 ---
    print("\nProcesando Query 1...")
    q1 = (trans_usd
        .filter(pl.col("Amount Paid") < 50)
        .select(["From Bank", "Account", "To Bank", "Account.1", "Amount Paid"])
        .collect()
    )
    q1.write_csv(str(outputs[1]))
    print(f"Query 1 guardada en: {outputs[1]} ({len(q1)} filas)")

    # --- Query 2 ---
    print("\nProcesando Query 2...")
    # Máxima transacción por banco origen, luego join con nombres de banco
    max_por_banco = (trans_usd
        .group_by("From Bank")
        .agg(pl.col("Amount Paid").max().alias("_max"))
    )
    q2 = (trans_usd
        .join(max_por_banco, on="From Bank")
        .filter(pl.col("Amount Paid") == pl.col("_max"))
        .drop("_max")
        .join(
            accounts_lazy.rename({"Bank ID": "From Bank"}),
            on="From Bank"
        )
        .select(["From Bank", "Account", "Bank Name", "Amount Paid"])
        .unique()
        .collect()
    )
    q2.write_csv(str(outputs[2]))
    print(f"Query 2 guardada en: {outputs[2]} ({len(q2)} filas)")

    # --- Query 3 ---
    print("\nProcesando Query 3...")
    avg_por_formato = (trans_usd_sept_1st
        .lazy()
        .group_by("Payment Format")
        .agg(pl.col("Amount Paid").mean().alias("AVG"))
    )
    trans_usd_sept_2nd = trans_usd.filter(
        (pl.col("Timestamp") >= "2022/09/06") & (pl.col("Timestamp") <= "2022/09/15")
    )
    q3 = (trans_usd_sept_2nd
        .join(avg_por_formato, on="Payment Format")
        .filter(pl.col("Amount Paid") < pl.col("AVG") * 0.01)
        .select(["From Bank", "Account", "Payment Format", "Amount Paid"])
        .collect()
    )
    q3.write_csv(str(outputs[3]))
    print(f"Query 3 guardada en: {outputs[3]} ({len(q3)} filas)")

    # --- Query 4 ---
    print("\nProcesando Query 4...")
    sept_1st = trans_usd_sept_1st.lazy()

    # Cuentas origen con más de 5 destinatarios distintos (To Bank, Account.1)
    n_destinos = (sept_1st
        .group_by(["From Bank", "Account", "To Bank", "Account.1"])
        .agg(pl.len())
        .group_by(["From Bank", "Account"])
        .agg(pl.len().alias("n_distinct"))
        .filter(pl.col("n_distinct") > 5)
        .select(["From Bank", "Account"])
    )

    accounts_ab = (sept_1st
        .join(n_destinos, on=["From Bank", "Account"])
        .select(["From Bank", "Account", "To Bank", "Account.1"])
    )
    accounts_bc = sept_1st.select(["From Bank", "Account", "To Bank", "Account.1"])

    # Join A→B con B→C para encontrar cadenas de tres cuentas
    # Polars descarta las columnas clave del lado derecho y agrega sufijo _right a las que colisionan
    pares = (accounts_ab
        .join(accounts_bc, left_on=["To Bank", "Account.1"], right_on=["From Bank", "Account"])
        .rename({
            "Account": "From Account",
            "To Bank": "Inter Bank",
            "Account.1": "Inter Account",
            "To Bank_right": "To Bank",
            "Account.1_right": "To Account",
        })
        .filter(
            (pl.col("From Bank") != pl.col("To Bank")) |
            (pl.col("From Account") != pl.col("To Account"))
        )
        .unique(subset=["From Bank", "From Account", "Inter Bank", "Inter Account", "To Bank", "To Account"])
        .group_by(["From Bank", "From Account", "To Bank", "To Account"])
        .agg(pl.len().alias("size"))
        .filter(pl.col("size") > 5)
        .collect()
    )

    q4 = pl.concat([
        pares.select([pl.col("From Bank").alias("Bank"), pl.col("From Account").alias("Account")]),
        pares.select([pl.col("To Bank").alias("Bank"), pl.col("To Account").alias("Account")]),
    ]).unique()
    q4.write_csv(str(outputs[4]))
    print(f"Query 4 guardada en: {outputs[4]} ({len(q4)} filas)")

    # --- Query 5 ---
    print("\nProcesando Query 5...")
    tasas_df = obtener_tasas_cambio()

    # Las transacciones de todos los formatos (no solo USD) en el período
    trans_sept_1st_wire_ach = (trans_lazy
        .filter(
            (pl.col("Timestamp") >= "2022/09/01") & (pl.col("Timestamp") <= "2022/09/06")
        )
        .filter(pl.col("Payment Format").is_in(["Wire", "ACH"]))
        .with_columns(
            pl.col("Timestamp").str.slice(0, 10).alias("Date")
        )
    )

    q5 = (trans_sept_1st_wire_ach
        .join(tasas_df.lazy(), on=["Date", "Payment Currency"])
        .with_columns(
            (pl.col("Amount Paid") / pl.col("rate")).alias("Amount USD")
        )
        .filter(pl.col("Amount USD") < 1.0)
        .collect()
    )
    count = len(q5)
    pl.DataFrame({"count": [count]}).write_csv(str(outputs[5]))
    print(f"Query 5 guardada en: {outputs[5]} (Valor: {count})")

    print("\n¡Ejecución de queries completada con éxito!")


if __name__ == "__main__":
    main()
