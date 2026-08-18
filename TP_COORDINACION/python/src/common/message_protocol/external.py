from asyncio import IncompleteReadError

from . import external_serializer


class MsgType:
    FRUIT_RECORD = 1
    FRUIT_TOP = 2
    ACK = 3
    END_OF_RECODS = 4


def _recv_sized(socket, size):
    """
    Receives exactly 'num_bytes' bytes through the provided socket.
    If no bytes are read from the socket IncompleteReadError is raised
    """
    buf = bytearray(size)
    pos = 0
    while pos < size:
        n = socket.recv_into(memoryview(buf)[pos:])
        if n == 0:
            raise IncompleteReadError(bytes(buf[:pos]), size)
        pos += n
    return bytes(buf)


def _recv_fruit_record(socket):
    fruit_size = external_serializer.deserialize_uint32(
        _recv_sized(socket, external_serializer.UINT32_SIZE)
    )
    fruit = external_serializer.deserialize_string(_recv_sized(socket, fruit_size))
    amount = external_serializer.deserialize_uint32(
        _recv_sized(socket, external_serializer.UINT32_SIZE)
    )
    return (fruit, amount)


def _recv_fruit_top(socket):
    fruit_top_size = external_serializer.deserialize_uint32(
        _recv_sized(socket, external_serializer.UINT32_SIZE)
    )
    fruit_top = []
    for i in range(fruit_top_size):
        fruit_record = _recv_fruit_record(socket)
        fruit_top.append(fruit_record)
    return fruit_top


def _recv_empty(socket):
    return None


RECV_MSG_HANDLERS = {
    MsgType.FRUIT_RECORD: _recv_fruit_record,
    MsgType.FRUIT_TOP: _recv_fruit_top,
    MsgType.ACK: _recv_empty,
    MsgType.END_OF_RECODS: _recv_empty,
}


def recv_msg(socket):
    msg_type = external_serializer.deserialize_uint32(
        _recv_sized(socket, external_serializer.UINT32_SIZE)
    )
    msg_handler = RECV_MSG_HANDLERS[msg_type]
    return (msg_type, msg_handler(socket))


def _serialize_fruit_record(fruit, amount):
    return b"".join(
        [
            external_serializer.serialize_uint32(len(fruit)),
            external_serializer.serialize_string(fruit),
            external_serializer.serialize_uint32(amount),
        ]
    )


def _send_fruit_record(socket, fruit, amount):
    msg = external_serializer.serialize_uint32(MsgType.FRUIT_RECORD)
    msg += _serialize_fruit_record(fruit, amount)
    socket.sendall(msg)


def _send_fruit_top(socket, fruit_top):
    msg = external_serializer.serialize_uint32(MsgType.FRUIT_TOP)
    msg += external_serializer.serialize_uint32(len(fruit_top))
    for fruit_record in fruit_top:
        msg += _serialize_fruit_record(*fruit_record)
    socket.sendall(msg)


def _send_ack(socket):
    socket.sendall(external_serializer.serialize_uint32(MsgType.ACK))


def _send_end_of_records(socket):
    socket.sendall(external_serializer.serialize_uint32(MsgType.END_OF_RECODS))


SEND_MSG_HANDLERS = {
    MsgType.FRUIT_RECORD: _send_fruit_record,
    MsgType.FRUIT_TOP: _send_fruit_top,
    MsgType.ACK: _send_ack,
    MsgType.END_OF_RECODS: _send_end_of_records,
}


def send_msg(socket, msg_type, *args):
    msg_handler = SEND_MSG_HANDLERS[msg_type]
    msg_handler(socket, *args)
