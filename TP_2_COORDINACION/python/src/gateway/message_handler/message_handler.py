from common import message_protocol

AMOUNT_OF_FIELDS_IN_RESULT_MESSAGE = 2

class MessageHandler:
    _next_id = 0

    def __init__(self):
        self.client_id = MessageHandler._next_id
        MessageHandler._next_id += 1

    def serialize_data_message(self, message):
        [fruit, amount] = message
        return message_protocol.internal.serialize([self.client_id, fruit, amount])

    def serialize_eof_message(self, message):
        return message_protocol.internal.serialize([self.client_id])

    def deserialize_result_message(self, message):
        fields = message_protocol.internal.deserialize(message)

        if self._is_a_result_message(fields):
            result_client_id, fruit_top = fields
            if result_client_id == self.client_id:
                return fruit_top
            return None

        return fields
    
    def _is_a_result_message(self, fields):
        return (
            isinstance(fields, list)
            and len(fields) == AMOUNT_OF_FIELDS_IN_RESULT_MESSAGE
            and isinstance(fields[0], int)
            and isinstance(fields[1], list)
        )
