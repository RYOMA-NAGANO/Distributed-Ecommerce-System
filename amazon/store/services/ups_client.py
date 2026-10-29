import hashlib
import json
from urllib import error, request
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone

from store.models import HttpDirection, HttpIdempotencyRecord, Shipment

REQUEST_TIMEOUT_SECONDS = 10


class UpsClientError(Exception):
    def __init__(self, message: str, status_code: int | None = None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


def fetch_world_id() -> int:
    response = _get_json("/world", expected_statuses={200})
    world_id = response.get("world_id")
    if world_id is None:
        raise UpsClientError("UPS /world response missing world_id", response_body=response)
    return int(world_id)


def create_shipment(shipment: Shipment) -> dict:
    payload = {
        "shipment_id": shipment.shipment_id,
        "world_id": shipment.world_id,
        "amazon_order_id": shipment.order.amazon_order_id,
        "warehouse": {
            "id": shipment.warehouse.warehouse_id,
            "x": shipment.warehouse.x,
            "y": shipment.warehouse.y,
        },
        "destination": {
            "x": shipment.destination_x,
            "y": shipment.destination_y,
        },
        "ups_account": shipment.order.ups_account or "",
        "items": [
            {
                "product_id": item.product.product_id,
                "description": item.description_snapshot,
                "quantity": item.quantity,
            }
            for item in shipment.items.select_related("product")
        ],
    }
    return _post_json("/shipments", payload, shipment=shipment, expected_statuses={200, 201})


def request_pickup(shipment: Shipment, priority: str = "normal") -> dict:
    payload = {
        "warehouse_id": shipment.warehouse.warehouse_id,
        "priority": priority,
        "world_id": shipment.world_id,
    }
    return _post_json(
        f"/shipments/{shipment.shipment_id}/pickup",
        payload,
        shipment=shipment,
        expected_statuses={200},
    )


def notify_ready(shipment: Shipment) -> dict:
    payload = {
        "warehouse_id": shipment.warehouse.warehouse_id,
        "world_id": shipment.world_id,
    }
    return _post_json(
        f"/shipments/{shipment.shipment_id}/ready",
        payload,
        shipment=shipment,
        expected_statuses={200},
    )


def notify_loaded(shipment: Shipment) -> dict:
    payload = {
        "truck_id": shipment.truck_id,
        "warehouse_id": shipment.warehouse.warehouse_id,
        "world_id": shipment.world_id,
    }
    return _post_json(
        f"/shipments/{shipment.shipment_id}/loaded",
        payload,
        shipment=shipment,
        expected_statuses={200},
    )


def notify_load_failed(shipment: Shipment, reason: str = "") -> dict:
    payload = {
        "truck_id": shipment.truck_id,
        "warehouse_id": shipment.warehouse.warehouse_id,
        "world_id": shipment.world_id,
        "reason": reason or "World rejected the load command.",
    }
    return _post_json(
        f"/shipments/{shipment.shipment_id}/load-failed",
        payload,
        shipment=shipment,
        expected_statuses={200},
    )


def _post_json(path: str, payload: dict, *, shipment: Shipment | None, expected_statuses: set[int]) -> dict:
    ups_base_url = (getattr(settings, "UPS_BASE_URL", "") or "").rstrip("/")
    ups_interop_secret = (getattr(settings, "UPS_INTEROP_SECRET", "") or "").strip()

    if not ups_base_url:
        raise UpsClientError("UPS_BASE_URL is not configured")

    # Serialize deterministically so the same logical request always hashes the
    # same way, regardless of dict ordering.
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body_hash = hashlib.sha256(body).hexdigest()
    # Stable Idempotency-Key per logical (method, path, body). Retries of the
    # same request now reuse the key so UPS can deduplicate them, instead of
    # minting a fresh uuid on every attempt.
    idempotency_key = hashlib.sha256(
        f"POST:{path}:{body_hash}".encode("utf-8")
    ).hexdigest()

    record, _created = HttpIdempotencyRecord.objects.get_or_create(
        direction=HttpDirection.OUTBOUND,
        method="POST",
        path=path,
        idempotency_key=idempotency_key,
        defaults={"peer": "ups", "body_hash": body_hash, "shipment": shipment},
    )
    # If a previous attempt already succeeded, replay the stored response
    # instead of re-sending the command (sender-side idempotency).
    if record.response_status in expected_statuses and record.response_body is not None:
        return record.response_body

    headers = {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotency_key,
    }
    if ups_interop_secret:
        headers["Authorization"] = f"Bearer {ups_interop_secret}"

    req = request.Request(
        urljoin(f"{ups_base_url}/", path.lstrip("/")),
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        timeout_seconds = int(getattr(settings, "UPS_TIMEOUT_SECONDS", REQUEST_TIMEOUT_SECONDS))
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            parsed_body = json.loads(response_body) if response_body else {}
            record.response_status = response.status
            record.response_body = parsed_body
            record.processed_at = timezone.now()
            record.save(update_fields=["response_status", "response_body", "processed_at", "updated_at"])

            if response.status not in expected_statuses:
                raise UpsClientError(
                    f"Unexpected UPS status {response.status}",
                    status_code=response.status,
                    response_body=parsed_body,
                )

            return parsed_body
    except error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8")
        try:
            parsed_body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            parsed_body = {"detail": raw_body}

        record.response_status = exc.code
        record.response_body = parsed_body
        record.processed_at = timezone.now()
        record.save(update_fields=["response_status", "response_body", "processed_at", "updated_at"])
        raise UpsClientError(
            f"UPS request failed with status {exc.code}",
            status_code=exc.code,
            response_body=parsed_body,
        ) from exc
    except error.URLError as exc:
        record.response_status = 0
        record.response_body = {"detail": str(exc.reason)}
        record.processed_at = timezone.now()
        record.save(update_fields=["response_status", "response_body", "processed_at", "updated_at"])
        raise UpsClientError(f"UPS request failed: {exc.reason}") from exc


def _get_json(path: str, *, expected_statuses: set[int]) -> dict:
    ups_base_url = (getattr(settings, "UPS_BASE_URL", "") or "").rstrip("/")
    ups_interop_secret = (getattr(settings, "UPS_INTEROP_SECRET", "") or "").strip()
    if not ups_base_url:
        raise UpsClientError("UPS_BASE_URL is not configured")

    headers = {}
    if ups_interop_secret:
        headers["Authorization"] = f"Bearer {ups_interop_secret}"

    req = request.Request(
        urljoin(f"{ups_base_url}/", path.lstrip("/")),
        headers=headers,
        method="GET",
    )
    try:
        timeout_seconds = int(getattr(settings, "UPS_TIMEOUT_SECONDS", REQUEST_TIMEOUT_SECONDS))
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
            parsed_body = json.loads(response_body) if response_body else {}
            if response.status not in expected_statuses:
                raise UpsClientError(
                    f"Unexpected UPS status {response.status}",
                    status_code=response.status,
                    response_body=parsed_body,
                )
            return parsed_body
    except error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8")
        try:
            parsed_body = json.loads(raw_body) if raw_body else {}
        except json.JSONDecodeError:
            parsed_body = {"detail": raw_body}
        raise UpsClientError(
            f"UPS request failed with status {exc.code}",
            status_code=exc.code,
            response_body=parsed_body,
        ) from exc
    except error.URLError as exc:
        raise UpsClientError(f"UPS request failed: {exc.reason}") from exc
