import json
import socket
from dataclasses import dataclass

from django.conf import settings
from google.protobuf.internal.decoder import _DecodeVarint32
from google.protobuf.internal.encoder import _VarintBytes

from protos import world_ups_pb2


class WorldConnectionError(Exception):
    pass


@dataclass
class WorldHandshakeResult:
    host: str
    port: int
    world_id: int
    result: str
    truck_count: int


def build_connect_message():
    connect = world_ups_pb2.UConnect()
    if settings.WORLD_ID:
        connect.worldid = int(settings.WORLD_ID)
    connect.isAmazon = False

    for truck in json.loads(settings.UPS_TRUCKS):
        init_truck = connect.trucks.add()
        init_truck.id = truck["id"]
        init_truck.x = truck["x"]
        init_truck.y = truck["y"]

    return connect


def _recv_exact(sock, byte_count):
    chunks = []
    remaining = byte_count

    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            raise WorldConnectionError("Socket closed before full protobuf message was received.")
        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def _recv_varint_prefixed_message(sock, message_cls):
    size_bytes = bytearray()
    while True:
        chunk = sock.recv(1)
        if not chunk:
            raise WorldConnectionError("Socket closed before protobuf length prefix was received.")
        size_bytes.extend(chunk)
        if chunk[0] < 0x80:
            break
        if len(size_bytes) > 5:
            raise WorldConnectionError("Received invalid protobuf length prefix from World server.")

    message_size, _ = _DecodeVarint32(size_bytes, 0)
    payload = _recv_exact(sock, message_size)
    message = message_cls()
    message.ParseFromString(payload)
    return message


def send_message(sock, message):
    payload = message.SerializeToString()
    sock.sendall(_VarintBytes(len(payload)) + payload)


def receive_connected(sock):
    return _recv_varint_prefixed_message(sock, world_ups_pb2.UConnected)


def connect_and_handshake(timeout=10):
    connect_message = build_connect_message()
    try:
        with socket.create_connection((settings.WORLD_HOST, settings.WORLD_PORT), timeout=timeout) as sock:
            send_message(sock, connect_message)
            connected = receive_connected(sock)
    except OSError as exc:
        raise WorldConnectionError(
            f"Failed to connect to World server at {settings.WORLD_HOST}:{settings.WORLD_PORT}: {exc}"
        ) from exc

    return WorldHandshakeResult(
        host=settings.WORLD_HOST,
        port=settings.WORLD_PORT,
        world_id=connected.worldid,
        result=connected.result,
        truck_count=len(connect_message.trucks),
    )
