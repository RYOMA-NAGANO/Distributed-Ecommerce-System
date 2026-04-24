import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

RETRY_INTERVAL = int(os.getenv("ACK_RETRY_INTERVAL_SECONDS", "5"))  # seconds between retries
MAX_RETRIES = int(os.getenv("ACK_MAX_RETRIES", "200"))


class AckManager:
    """
    Tracks outgoing commands that need acknowledgement from the world simulator.

    Usage:
        mgr = AckManager(send_fn=client.send)
        seqnum = mgr.next_seqnum()
        # build your ACommands with that seqnum
        mgr.register(seqnum, commands)
        # when AResponses.acks contains seqnum:
        mgr.ack(seqnum)
    """

    def __init__(self, send_fn):
        self._send_fn = send_fn
        self._lock = threading.Lock()
        self._pending = {}      # seqnum -> {cmd, retries, last_sent}
        # World may keep enough connection/world state that reusing low seqnums
        # after a daemon restart can produce confusing acks without the matching
        # business response. Start from epoch milliseconds to avoid reuse across
        # restarts without adding another persistence table.
        self._counter = int(time.time() * 1000)
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._retry_loop, name="ack-retry", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False

    def next_seqnum(self) -> int:
        with self._lock:
            self._counter += 1
            return self._counter

    def register(
        self,
        seqnum: int,
        commands,
        *,
        retry_enabled: bool = True,
        retry_interval: int = RETRY_INTERVAL,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        with self._lock:
            self._pending[seqnum] = {
                "cmd": commands,
                "retries": 0,
                "last_sent": time.monotonic(),
                "retry_enabled": retry_enabled,
                "retry_interval": retry_interval,
                "max_retries": max_retries,
            }

    def ack(self, seqnum: int) -> None:
        with self._lock:
            self._pending.pop(seqnum, None)

    def ack_many(self, seqnums) -> None:
        with self._lock:
            for s in seqnums:
                self._pending.pop(s, None)

    def _retry_loop(self) -> None:
        while self._running:
            time.sleep(1)
            now = time.monotonic()
            with self._lock:
                to_retry = [
                    (seq, info)
                    for seq, info in self._pending.items()
                    if info.get("retry_enabled", True)
                    and now - info["last_sent"] >= info.get("retry_interval", RETRY_INTERVAL)
                ]
            for seq, info in to_retry:
                if info["retries"] >= info.get("max_retries", MAX_RETRIES):
                    logger.error("seqnum %d exceeded max retries, dropping", seq)
                    with self._lock:
                        self._pending.pop(seq, None)
                    continue
                logger.warning("retrying seqnum %d (attempt %d)", seq, info["retries"] + 1)
                try:
                    self._send_fn(info["cmd"])
                    with self._lock:
                        if seq in self._pending:
                            self._pending[seq]["retries"] += 1
                            self._pending[seq]["last_sent"] = time.monotonic()
                except Exception as exc:
                    logger.error("retry send failed for seqnum %d: %s", seq, exc)
