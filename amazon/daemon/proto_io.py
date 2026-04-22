import socket


def send_message(sock: socket.socket, message) -> None:
    data = message.SerializeToString()
    size = len(data)
    varint_bytes = []
    while True:
        bits = size & 0x7F
        size >>= 7
        if size:
            varint_bytes.append(0x80 | bits)
        else:
            varint_bytes.append(bits)
            break
    sock.sendall(bytes(varint_bytes) + data)


def recv_message(sock: socket.socket, message_class):
    result = 0
    shift = 0
    while True:
        b = sock.recv(1)
        if not b:
            raise ConnectionError("connection closed while reading varint")
        byte = b[0]
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            break
        shift += 7

    size = result
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise ConnectionError("connection closed while reading message body")
        data.extend(chunk)

    msg = message_class()
    msg.ParseFromString(bytes(data))
    return msg
