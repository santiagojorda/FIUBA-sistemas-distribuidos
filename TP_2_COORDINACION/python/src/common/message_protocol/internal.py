import json


def serialize(message):
    return json.dumps(message).encode("utf-8")


def deserialize(message):
    return json.loads(message.decode("utf-8"))


def serialize_control(client_id):
    return serialize({"client_id": int(client_id)})


def deserialize_control(message):
    fields = deserialize(message)

    if isinstance(fields, list):
        if len(fields) != 1:
            raise ValueError("Invalid control payload list format")
        return (int(fields[0]),)

    if isinstance(fields, dict) and "client_id" in fields:
        return (int(fields["client_id"]),)

    raise ValueError("Invalid control payload format")
