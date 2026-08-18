import re
from pathlib import Path

def obtener_queries_desde_compose(ruta_compose=None):
    if ruta_compose is None:
        ruta_compose = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    else:
        ruta_compose = Path(ruta_compose)
        if not ruta_compose.is_absolute():
            candidato_local = Path(__file__).resolve().parent / ruta_compose
            candidato_repo = Path(__file__).resolve().parents[2] / ruta_compose
            if candidato_local.exists():
                ruta_compose = candidato_local
            elif candidato_repo.exists():
                ruta_compose = candidato_repo

    texto = ruta_compose.read_text(encoding="utf-8")
    service_names = re.findall(r"(?m)^\s{2}([A-Za-z0-9_-]+):\s*$", texto)
    query_ids = set()
    for service_name in service_names:
        match = re.match(r"^q(\d+)_", service_name)
        if match:
            query_ids.add(int(match.group(1)))
    if not query_ids:
        raise ValueError("No se encontraron queries en el docker-compose.yml")
    return sorted(query_ids)