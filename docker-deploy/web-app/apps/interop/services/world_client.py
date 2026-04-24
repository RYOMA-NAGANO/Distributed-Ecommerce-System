import socket
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

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


@dataclass
class WorldSession:
    sock: socket.socket
    handshake: WorldHandshakeResult


def _initial_spawn_for_truck(truck_id: int) -> tuple[int, int]:
    # Deterministic spawn positions for world creation handshake only.
    idx = max(0, int(truck_id) - 1)
    return (1 + (idx % 4) * 4, 1 + (idx // 4) * 4)


def build_connect_message(world_id_override: int | None = None):
    connect = world_ups_pb2.UConnect()
    if world_id_override is not None:
        connect.worldid = int(world_id_override)
    elif settings.WORLD_ID:
        connect.worldid = int(settings.WORLD_ID)
    connect.isAmazon = False

    # UInitTruck exists only on connect; initialize from UPS's persisted truck ids.
    # If joining an existing world id, we do not redefine truck pool here.
    if not connect.HasField("worldid"):
        from apps.core.models import Truck

        known_ids = list(
            Truck.objects.exclude(truck_status=Truck.TruckStatus.INVALID)
            .order_by("truck_id")
            .values_list("truck_id", flat=True)
        )
        if not known_ids:
            truck, _ = Truck.objects.get_or_create(
                truck_id=1,
                defaults={"truck_status": Truck.TruckStatus.IDLE},
            )
            known_ids = [int(truck.truck_id)]

        for truck_id in known_ids:
            init_truck = connect.trucks.add()
            init_truck.id = int(truck_id)
            x, y = _initial_spawn_for_truck(int(truck_id))
            init_truck.x = int(x)
            init_truck.y = int(y)

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


def receive_responses(sock):
    return _recv_varint_prefixed_message(sock, world_ups_pb2.UResponses)


def collect_response_seqnums(responses) -> list[int]:
    seqnums: list[int] = []

    for msg in responses.completions:
        seqnums.append(int(msg.seqnum))
    for msg in responses.delivered:
        seqnums.append(int(msg.seqnum))
    for msg in responses.truckstatus:
        seqnums.append(int(msg.seqnum))
    for msg in responses.error:
        seqnums.append(int(msg.seqnum))

    # Only ack concrete response messages from World.
    return list(dict.fromkeys(seqnums))


def build_commands_with_acks(extra_acks: Optional[Iterable[int]] = None) -> world_ups_pb2.UCommands:
    commands = world_ups_pb2.UCommands()
    if extra_acks:
        for seq in extra_acks:
            commands.acks.append(int(seq))
    return commands


def send_pickup(sock, truck_id: int, warehouse_id: int, seqnum: int, acks: Optional[Iterable[int]] = None):
    commands = build_commands_with_acks(acks)
    pickup = commands.pickups.add()
    pickup.truckid = int(truck_id)
    pickup.whid = int(warehouse_id)
    pickup.seqnum = int(seqnum)
    send_message(sock, commands)


def send_deliver(sock, truck_id: int, world_package_id: int, dest_x: int, dest_y: int, seqnum: int, acks: Optional[Iterable[int]] = None):
    commands = build_commands_with_acks(acks)
    delivery = commands.deliveries.add()
    delivery.truckid = int(truck_id)
    delivery.seqnum = int(seqnum)

    pkg = delivery.packages.add()
    pkg.packageid = int(world_package_id)
    pkg.x = int(dest_x)
    pkg.y = int(dest_y)

    send_message(sock, commands)


def send_query(sock, truck_id: int, seqnum: int, acks: Optional[Iterable[int]] = None):
    commands = build_commands_with_acks(acks)
    query = commands.queries.add()
    query.truckid = int(truck_id)
    query.seqnum = int(seqnum)
    send_message(sock, commands)


def send_acks_only(sock, acks: Iterable[int]):
    commands = build_commands_with_acks(acks)
    send_message(sock, commands)


def format_responses(responses):
    parts = []

    if responses.completions:
        parts.append(f"completions={len(responses.completions)}")
    if responses.delivered:
        parts.append(f"delivered={len(responses.delivered)}")
    if responses.truckstatus:
        parts.append(f"truckstatus={len(responses.truckstatus)}")
    if responses.error:
        parts.append(f"errors={len(responses.error)}")
    if responses.acks:
        parts.append(f"acks={len(responses.acks)}")
    if responses.finished:
        parts.append("finished=true")

    return ", ".join(parts) if parts else "empty response"


def open_world_session(connect_timeout=10, read_timeout=2.0, world_id: int | None = None):
    connect_message = build_connect_message(world_id_override=world_id)
    sock = None
    try:
        sock = socket.create_connection((settings.WORLD_HOST, settings.WORLD_PORT), timeout=connect_timeout)
        sock.settimeout(connect_timeout)
        send_message(sock, connect_message)
        connected = receive_connected(sock)
    except OSError as exc:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        raise WorldConnectionError(
            f"Failed to connect to World server at {settings.WORLD_HOST}:{settings.WORLD_PORT}: {exc}"
        ) from exc
    except WorldConnectionError:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        raise

    if connected.result != "connected!":
        try:
            sock.close()
        except Exception:
            pass
        raise WorldConnectionError(
            f"World rejected UPS connection for world_id={world_id}: {connected.result}"
        )

    sock.settimeout(float(read_timeout))

    return WorldSession(
        sock=sock,
        handshake=WorldHandshakeResult(
            host=settings.WORLD_HOST,
            port=settings.WORLD_PORT,
            world_id=connected.worldid,
            result=connected.result,
            truck_count=len(connect_message.trucks),
        ),
    )


def connect_and_handshake(timeout=10):
    session = open_world_session(connect_timeout=timeout, read_timeout=timeout)
    try:
        return session.handshake
    finally:
        session.sock.close()


def listen_for_world_events(
    timeout=10,
    on_response: Optional[Callable[[object], None]] = None,
    on_idle: Optional[Callable[[], None]] = None,
):
    session = open_world_session(connect_timeout=timeout, read_timeout=timeout)
    try:
        while True:
            try:
                responses = receive_responses(session.sock)
            except socket.timeout:
                if on_idle is not None:
                    on_idle()
                continue

            if on_response is not None:
                on_response(responses)
    finally:
        session.sock.close()


def query_truck_status(
    *,
    truck_id: int,
    world_id: int | None = None,
    timeout: float = 1.0,
    retries: int = 2,
) -> dict | None:
    from apps.interop.services.seqnum import allocate_next_seqnum

    session = open_world_session(
        connect_timeout=max(0.2, float(timeout)),
        read_timeout=max(0.2, float(timeout)),
        world_id=world_id,
    )
    try:
        query_seq = allocate_next_seqnum()
        send_query(session.sock, truck_id=int(truck_id), seqnum=int(query_seq))
        deadline = time.monotonic() + max(0.2, float(timeout))

        while time.monotonic() < deadline:
            try:
                responses = receive_responses(session.sock)
            except socket.timeout:
                continue

            acks = collect_response_seqnums(responses)
            if acks:
                send_acks_only(session.sock, acks)

            for truck in responses.truckstatus:
                if int(truck.truckid) == int(truck_id):
                    return {
                        "truck_id": int(truck.truckid),
                        "x": int(truck.x),
                        "y": int(truck.y),
                        "status": str(truck.status or ""),
                        "seqnum": int(truck.seqnum),
                    }

        if retries <= 0:
            return None
    finally:
        session.sock.close()

    return query_truck_status(
        truck_id=int(truck_id),
        world_id=world_id,
        timeout=timeout,
        retries=retries - 1,
    )
