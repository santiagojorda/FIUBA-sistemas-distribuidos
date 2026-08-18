class EstadoClienteCoordinacion:
    def __init__(self):
        self.eofs_locales = set()
        self.eof_local_completo = False
        self.originador = None
        self.barrera_activa = False
        self.workers_confirmados = set()
        self.worker_conteos = {}
        self.mensaje_original = None
        self.flusheado = False
        self.flush_en_progreso = False
        self.originador_flush = None
        self.finalizado = False

    def marcar_finalizado(self):
        self.eofs_locales.clear()
        self.eof_local_completo = False
        self.originador = None
        self.barrera_activa = False
        self.workers_confirmados.clear()
        self.worker_conteos.clear()
        self.mensaje_original = None
        self.flusheado = False
        self.flush_en_progreso = False
        self.originador_flush = None
        self.finalizado = True

    def desactivar_barrera(self):
        self.barrera_activa = False
        self.workers_confirmados.clear()
        self.worker_conteos.clear()
        self.mensaje_original = None
