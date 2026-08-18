TAMANIO_UINT32 = 4
TAMANIO_BOOL = 1


def serializar_bool(u):
    return int(u).to_bytes(TAMANIO_BOOL, "big")


def deserializar_bool(b):
    return int.from_bytes(b, byteorder="big", signed=False)


def serializar_uint32(u):
    return u.to_bytes(TAMANIO_UINT32, "big")


def deserializar_uint32(b):
    return int.from_bytes(b, byteorder="big", signed=False)


def deserializar_string(b):
    return b.decode("utf-8")


def serializar_string(s):
    return s.encode("utf-8")
