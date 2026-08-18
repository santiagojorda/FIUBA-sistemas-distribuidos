#!/usr/bin/env python3
import argparse
import csv
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_INPUT_DATASET = "datasets/trans_sample.csv"
DEFAULT_OUTPUT_DATASET = "datasets/transacciones_sample_q4.csv"
DEFAULT_FANOUT = 6
DEFAULT_TIMESTAMP = "2022/09/02 10:00"
DEFAULT_AMOUNT = 1000.0
DEFAULT_CURRENCY = "US Dollar"
DEFAULT_IS_LAUNDERING = "1"

REQUIRED_COLUMNS = [
    "Timestamp",
    "From Bank",
    "Account",
    "To Bank",
    "Account.1",
    "Amount Received",
    "Receiving Currency",
    "Amount Paid",
    "Payment Currency",
    "Payment Format",
    "Is Laundering",
]

DEFAULT_PAYMENT_FORMATS = ["Wire", "ACH", "Cheque", "Credit Card", "Cash", "Reinvestment"]

HEADER_ALIASES = {
    "From Account": "Account",
    "To Account": "Account.1",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Copia un dataset CSV de transacciones y le inyecta un patron scatter-gather "
            "del tipo A->B_i y B_i->C dentro de la ventana temporal de la query 4."
        )
    )
    parser.add_argument(
        "--input",
        default=DEFAULT_INPUT_DATASET,
        help=(
            "CSV de entrada. Si no se indica, usa el valor de "
            "DEFAULT_INPUT_DATASET dentro del script."
        ),
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT_DATASET,
        help=(
            "CSV de salida. Si no se indica, usa el valor de "
            "DEFAULT_OUTPUT_DATASET dentro del script."
        ),
    )
    parser.add_argument(
        "--fanout",
        type=int,
        default=DEFAULT_FANOUT,
        help=(
            "Cantidad de cuentas intermedias B. Usa 6 para que lo detecte "
            "notebook/notebook_catedra.ipynb y 5 solo para notebook/query4/query4.py."
        ),
    )
    parser.add_argument(
        "--timestamp",
        default=DEFAULT_TIMESTAMP,
        help="Timestamp base para las filas inyectadas, formato YYYY/MM/DD HH:MM",
    )
    parser.add_argument(
        "--amount",
        type=float,
        default=DEFAULT_AMOUNT,
        help="Monto para las transacciones inyectadas",
    )
    parser.add_argument(
        "--currency",
        default=DEFAULT_CURRENCY,
        help="Moneda para Amount Paid y Amount Received",
    )
    parser.add_argument(
        "--is-laundering",
        default=DEFAULT_IS_LAUNDERING,
        help="Valor de la columna Is Laundering en las filas nuevas",
    )
    return parser.parse_args()


def ensure_required_columns(fieldnames: list[str]) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"El CSV no tiene las columnas requeridas: {missing_str}")


def normalize_fieldnames(raw_fieldnames: list[str]) -> list[str]:
    normalized: list[str] = []
    seen_counts: dict[str, int] = {}

    for raw_name in raw_fieldnames:
        base_name = HEADER_ALIASES.get(raw_name, raw_name)
        count = seen_counts.get(base_name, 0)

        if base_name == "Account" and count == 1:
            normalized_name = "Account.1"
        elif count == 0:
            normalized_name = base_name
        else:
            normalized_name = f"{base_name}.{count}"

        seen_counts[base_name] = count + 1
        normalized.append(normalized_name)

    return normalized


def make_ids() -> dict[str, object]:
    token = uuid.uuid4().hex[:8].upper()
    source = ("990001", f"SG_SRC_{token}")
    target = ("990099", f"SG_DST_{token}")
    intermediates = [
        (str(990010 + index), f"SG_B_{token}_{index + 1:02d}")
        for index in range(64)
    ]
    return {
        "token": token,
        "source": source,
        "target": target,
        "intermediates": intermediates,
    }


def make_row(
    from_bank: str,
    from_account: str,
    to_bank: str,
    to_account: str,
    timestamp: datetime,
    amount: float,
    currency: str,
    payment_format: str,
    is_laundering: str,
) -> dict[str, str]:
    amount_str = f"{amount:.2f}"
    return {
        "Timestamp": timestamp.strftime("%Y/%m/%d %H:%M"),
        "From Bank": from_bank,
        "Account": from_account,
        "To Bank": to_bank,
        "Account.1": to_account,
        "Amount Received": amount_str,
        "Receiving Currency": currency,
        "Amount Paid": amount_str,
        "Payment Currency": currency,
        "Payment Format": payment_format,
        "Is Laundering": is_laundering,
    }


def generate_pattern_rows(
    fanout: int,
    start_timestamp: datetime,
    amount: float,
    currency: str,
    is_laundering: str,
) -> tuple[list[dict[str, str]], tuple[str, str], tuple[str, str], list[tuple[str, str]]]:
    ids = make_ids()
    source_bank, source_account = ids["source"]
    target_bank, target_account = ids["target"]
    intermediates = ids["intermediates"][:fanout]

    rows: list[dict[str, str]] = []
    for index, (mid_bank, mid_account) in enumerate(intermediates):
        scatter_time = start_timestamp + timedelta(minutes=index)
        gather_time = start_timestamp + timedelta(minutes=fanout + index)
        payment_format = DEFAULT_PAYMENT_FORMATS[index % len(DEFAULT_PAYMENT_FORMATS)]

        rows.append(
            make_row(
                from_bank=source_bank,
                from_account=source_account,
                to_bank=mid_bank,
                to_account=mid_account,
                timestamp=scatter_time,
                amount=amount + index,
                currency=currency,
                payment_format=payment_format,
                is_laundering=is_laundering,
            )
        )
        rows.append(
            make_row(
                from_bank=mid_bank,
                from_account=mid_account,
                to_bank=target_bank,
                to_account=target_account,
                timestamp=gather_time,
                amount=amount + fanout + index,
                currency=currency,
                payment_format=payment_format,
                is_laundering=is_laundering,
            )
        )

    return rows, ids["source"], ids["target"], intermediates


def copy_with_injection(
    input_path: Path,
    output_path: Path,
    injected_rows: list[dict[str, str]],
) -> int:
    original_rows = 0
    temp_output_path = output_path
    same_file = input_path.resolve() == output_path.resolve()

    if same_file:
        temp_output_path = output_path.with_name(f".{output_path.name}.tmp")

    with input_path.open("r", newline="", encoding="utf-8") as source_file:
        raw_reader = csv.reader(source_file)
        raw_fieldnames = next(raw_reader, None)
        if raw_fieldnames is None:
            raise ValueError("El CSV de entrada no tiene cabecera")
        fieldnames = normalize_fieldnames(raw_fieldnames)
        ensure_required_columns(fieldnames)

        output_headers = [
            "Account" if name == "Account.1" else name
            for name in fieldnames
        ]

        with temp_output_path.open("w", newline="", encoding="utf-8") as target_file:
            writer = csv.writer(target_file)
            writer.writerow(output_headers)

            for values in raw_reader:
                row_values = list(values)
                if len(row_values) < len(fieldnames):
                    row_values.extend([""] * (len(fieldnames) - len(row_values)))
                elif len(row_values) > len(fieldnames):
                    row_values = row_values[:len(fieldnames)]
                writer.writerow(row_values)
                original_rows += 1

            for row in injected_rows:
                row_values = [row.get(column, "") for column in fieldnames]
                writer.writerow(row_values)

    if same_file:
        os.replace(temp_output_path, output_path)

    return original_rows


def main() -> None:
    args = parse_args()

    if args.fanout < 2:
        raise SystemExit("--fanout debe ser al menos 2")
    if args.fanout > 64:
        raise SystemExit("--fanout no puede ser mayor a 64")

    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    start_timestamp = datetime.strptime(args.timestamp, "%Y/%m/%d %H:%M")
    injected_rows, source, target, intermediates = generate_pattern_rows(
        fanout=args.fanout,
        start_timestamp=start_timestamp,
        amount=args.amount,
        currency=args.currency,
        is_laundering=args.is_laundering,
    )

    original_rows = copy_with_injection(input_path, output_path, injected_rows)

    print(f"Archivo generado: {output_path}")
    print(f"Filas originales: {original_rows}")
    print(f"Filas inyectadas: {len(injected_rows)}")
    print(f"Fanout configurado: {args.fanout}")
    print(f"Cuenta origen A: bank={source[0]} account={source[1]}")
    print(f"Cuenta destino C: bank={target[0]} account={target[1]}")
    print("Cuentas intermedias B:")
    for bank, account in intermediates:
        print(f"  - bank={bank} account={account}")


if __name__ == "__main__":
    main()
