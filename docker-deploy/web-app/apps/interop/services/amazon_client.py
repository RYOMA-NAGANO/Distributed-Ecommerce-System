import logging
import uuid

import requests
from django.conf import settings

logger = logging.getLogger(__name__)


def _base() -> str:
    return getattr(settings, "AMAZON_BASE_URL", "") or ""


def _post(path: str, payload: dict) -> None:
    base = _base().rstrip("/")
    if not base:
        logger.info("AMAZON_BASE_URL not set; skip callback %s", path)
        return
    url = f"{base}{path}"
    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": str(uuid.uuid4()),
    }
    secret = getattr(settings, "AMAZON_INTEROP_SECRET", "") or ""
    if secret:
        headers["Authorization"] = f"Bearer {secret}"
    r = requests.post(url, json=payload, headers=headers, timeout=15)
    r.raise_for_status()


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


def notify_load_request(package) -> None:
    _post(
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
