from common import message_protocol

CANTIDAD_DE_CAMPOS_EN_MENSAJE_RESULTADO = 2

class MessageHandler:
    _siguiente_id = 0

    def __init__(self):
        self.client_id = MessageHandler._siguiente_id
        MessageHandler._siguiente_id += 1

    def serializar_mensaje_datos(self, mensaje):
        # Serializar dict de transacción con client_id
        payload = dict(mensaje)
        payload["client_id"] = self.client_id
        return message_protocol.internal.ParseadorMensajes.serializar(payload)

    def serializar_mensaje_eof(self, mensaje):
        # Los workers esperan un EOF con la forma {"client_id": ...}
        # Usar crear_eof para generar el formato correcto.
        return message_protocol.internal.crear_eof(self.client_id)

    def deserializar_mensaje_resultado(self, mensaje):
        campos = message_protocol.internal.ParseadorMensajes.deserializar(mensaje)

        if self._es_mensaje_resultado(campos):
            client_id_resultado, datos_resultado = campos
            if client_id_resultado == self.client_id:
                return datos_resultado
            return None

        return campos

    def _es_mensaje_resultado(self, campos):
        return (
            isinstance(campos, list)
            and len(campos) == CANTIDAD_DE_CAMPOS_EN_MENSAJE_RESULTADO
            and isinstance(campos[0], int)
            and isinstance(campos[1], list)
        )
