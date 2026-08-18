import pytest
from unittest.mock import patch, MagicMock
import requests
from workers.convertidor.cliente_cotizaciones import ClienteCotizaciones

def test_cliente_cotizaciones_exito_primer_intento():
    cliente = ClienteCotizaciones("2022-09-01", "2022-09-02")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "rates": {
            "2022-09-01": {"EUR": 1.0, "CAD": 1.3},
            "2022-09-02": {"EUR": 1.01, "CAD": 1.31}
        }
    }
    
    with patch("requests.get", return_value=mock_resp) as mock_get:
        cotizaciones = cliente.obtener_cotizaciones()
        assert mock_get.call_count == 1
        assert "2022-09-01" in cotizaciones
        assert cotizaciones["2022-09-01"]["EUR"] == 1.0

def test_cliente_cotizaciones_reintenta_y_logra_conectar():
    cliente = ClienteCotizaciones("2022-09-01", "2022-09-01")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "rates": {
            "2022-09-01": {"EUR": 0.95}
        }
    }
    
    # Falla las primeras 2 veces y luego funciona en la tercera
    with patch("requests.get", side_effect=[
        requests.exceptions.ConnectionError("Fallo DNS"),
        requests.exceptions.Timeout("Timeout"),
        mock_resp
    ]) as mock_get, patch("time.sleep") as mock_sleep:
        cotizaciones = cliente.obtener_cotizaciones()
        assert mock_get.call_count == 3
        assert mock_sleep.call_count == 2
        assert cotizaciones["2022-09-01"]["EUR"] == 0.95
