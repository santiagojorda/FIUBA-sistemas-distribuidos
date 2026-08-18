import os
import json


class ConfiguracionWatchdog:
    def __init__(self):
        self.host_mom = os.getenv("MOM_HOST", "localhost")
        self.etapas = json.loads(os.getenv("WATCHDOG_STAGES", "[]"))
        self.intervalo_latido_segundos = float(os.getenv("HEARTBEAT_INTERVAL_SECONDS", "5"))
        self.umbral_latidos_perdidos = int(os.getenv("MISSED_HEARTBEATS_THRESHOLD", "3"))
        self.intervalo_chequeo_segundos = float(os.getenv("CHECK_INTERVAL_SECONDS", "2"))
        self.cola_caidas = os.getenv("CAIDAS_QUEUE", "caidas")

        self.id_watchdog = int(os.getenv("WATCHDOG_ID", "1"))
        self.cantidad_watchdogs = int(os.getenv("NUM_WATCHDOGS", "3"))
        self.intervalo_latido_lider = float(os.getenv("LEADER_HEARTBEAT_INTERVAL", "5"))
        self.timeout_lider_segundos = float(os.getenv("LEADER_TIMEOUT_SECONDS", "20"))
        self.demora_inicial_eleccion_max = float(os.getenv("ELECTION_STARTUP_DELAY_MAX", "3"))
        self.intervalo_chequeo_lider = float(os.getenv("CHECK_LEADER_INTERVAL", "5"))
        self.timeout_eleccion = float(os.getenv("ELECTION_TIMEOUT", "30"))
        self.ttl_sospechados_caidos = float(os.getenv("SUSPECTED_DEAD_TTL", "60"))

    @property
    def timeout_segundos(self):
        return self.intervalo_latido_segundos * self.umbral_latidos_perdidos
