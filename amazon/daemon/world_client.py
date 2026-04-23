import logging
import os
import socket
import threading

from proto_io import send_message, recv_message
from world_amazon_pb2 import AConnect, AConnected, ACommands, AResponses

logger = logging.getLogger(__name__)

WORLD_HOST = os.getenv("WORLD_HOST", "localhost")
WORLD_PORT = int(os.getenv("WORLD_PORT", "23456"))


class WorldClient:
    """
    Manages a single TCP connection to the world simulator.

    Usage:
        client = WorldClient(on_response=my_handler)
        world_id = client.connect(world_id=None, warehouses=[(1, 2, 4)])
        client.send(commands)
        client.disconnect()

    on_response(AResponses) is called from a background thread for every
    message received from the world simulator.
    """

    def __init__(self, on_response):
        self._on_response = on_response
        self._sock = None
        self._send_lock = threading.Lock()
        self._connected = False
        self._recv_thread = None

    def connect(self, world_id, warehouses):
        """
        Connect and handshake with the world simulator.

        warehouses: list of (id, x, y) tuples
        world_id:   int to join an existing world, or None to create a new one

        Returns the world_id assigned by the simulator.
        """
        # When joining an existing world created by UPS, Amazon may still need to
        # register its warehouses. Try with initwh first; if World rejects that
        # (for example because warehouses already exist), fall back to join-only.
        if world_id is None:
            attempts = [True]
        else:
            attempts = [True, False]

        last_error = None
        for include_warehouses in attempts:
            sock = self._connect_socket()
            sock.settimeout(None)

            req = self._build_connect_request(
                world_id=world_id,
                warehouses=warehouses,
                include_warehouses=include_warehouses,
            )

            send_message(sock, req)
            resp = recv_message(sock, AConnected)

            if resp.result == "connected!":
                self._sock = sock
                self._connected = True
                logger.info(
                    "Connected to world %d (include_warehouses=%s)",
                    resp.worldid,
                    include_warehouses,
                )

                self._recv_thread = threading.Thread(
                    target=self._recv_loop, name="world-recv", daemon=True
                )
                self._recv_thread.start()
                return resp.worldid

            last_error = resp.result
            sock.close()
            logger.warning(
                "World connect rejected (include_warehouses=%s): %s",
                include_warehouses,
                resp.result,
            )

        raise ConnectionError(f"World rejected connection: {last_error}")

    @staticmethod
    def _build_connect_request(world_id, warehouses, include_warehouses: bool) -> AConnect:
        req = AConnect()
        req.isAmazon = True
        if world_id is not None:
            req.worldid = world_id

        if include_warehouses:
            for wh_id, x, y in warehouses:
                wh = req.initwh.add()
                wh.id = wh_id
                wh.x = x
                wh.y = y

        return req

    def _connect_socket(self):
        last_error = None

        for host in self._candidate_hosts():
            try:
                logger.info("Trying world connection host=%s port=%d", host, WORLD_PORT)
                return socket.create_connection((host, WORLD_PORT), timeout=30)
            except OSError as exc:
                last_error = exc
                logger.warning("World connection attempt failed host=%s: %s", host, exc)

        raise ConnectionError(
            f"Unable to connect to world simulator using hosts {self._candidate_hosts()}: {last_error}"
        )

    @staticmethod
    def _candidate_hosts():
        hosts = [WORLD_HOST]

        # In Docker-based local development, the world server is often exposed from
        # another stack or from the host machine rather than the current compose network.
        for fallback in ("host.docker.internal", "localhost"):
            if fallback not in hosts:
                hosts.append(fallback)

        return hosts

    def send(self, commands: ACommands) -> None:
        with self._send_lock:
            send_message(self._sock, commands)

    def disconnect(self) -> None:
        self._connected = False
        try:
            cmd = ACommands()
            cmd.disconnect = True
            self.send(cmd)
        except Exception:
            pass
        try:
            self._sock.close()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        return self._connected

    def _recv_loop(self) -> None:
        while self._connected:
            try:
                resp = recv_message(self._sock, AResponses)
                self._on_response(resp)
            except ConnectionError as exc:
                logger.warning("World connection lost: %s", exc)
                self._connected = False
                break
            except Exception as exc:
                logger.error("Unexpected error in recv loop: %s", exc)
                self._connected = False
                break
