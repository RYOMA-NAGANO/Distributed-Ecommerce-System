import hashlib
import json
import logging

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _base() -> str:
    return getattr(settings, "AMAZON_BASE_URL", "") or ""


def _derive_idempotency_key(path: str, body: str) -> str:
    """Stable key per logical callback (path + payload).

    Using a deterministic hash instead of a fresh uuid means retries of the
    same event carry the same Idempotency-Key, so Amazon can deduplicate them.
    """
    return hashlib.sha256(f"{path}:{body}".encode("utf-8")).hexdigest()


def _post(path: str, payload: dict, *, idempotency_key: str | None = None) -> dict:
    base = _base().rstrip("/")
    if not base:
        logger.info("AMAZON_BASE_URL not set; skip callback %s", path)
        return {}
    url = f"{base}{path}"
    # Serialize deterministically so the derived key is stable across retries.
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if idempotency_key is None:
        idempotency_key = _derive_idempotency_key(path, body)
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
    }
    secret = getattr(settings, "AMAZON_INTEROP_SECRET", "") or ""
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    r = requests.post(url, data=body.encode("utf-8"), headers=headers, timeout=15)
    r.raise_for_status()
    if not r.content:
        return {}
    return r.json()


def notify_truck_arrived(package, x: int, y: int) -> None:
    _post(
        "/api/truck-arrived",
        {
            "shipment_id": package.shipment_id,
            "truck_id": int(package.truck_id),
            "warehouse_id": int(package.warehouse_id),
            "location": {"x": int(x), "y": int(y)},
            "world_id": int(package.world_id),
        },
    )


def notify_load_request(package) -> dict:
    return _post(
        "/api/load-request",
        {
            "shipment_id": package.shipment_id,
            "truck_id": int(package.truck_id),
            "warehouse_id": int(package.warehouse_id),
            "world_id": int(package.world_id),
        },
    )


def notify_out_for_delivery(package) -> None:
    _post(
        "/api/out-for-delivery",
        {
            "shipment_id": package.shipment_id,
            "truck_id": int(package.truck_id),
            "destination": {"x": int(package.dest_x), "y": int(package.dest_y)},
            "world_id": int(package.world_id),
        },
    )


def notify_delivered(package, x: int, y: int) -> None:
    _post(
        "/api/delivered",
        {
            "shipment_id": package.shipment_id,
            "truck_id": int(package.truck_id),
            "location": {"x": int(x), "y": int(y)},
            "world_id": int(package.world_id),
        },
    )
