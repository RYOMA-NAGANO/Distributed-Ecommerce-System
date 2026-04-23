import logging
import os
import sys
import time

# Bootstrap Django before importing any store models.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amazon_web.settings")

import django
django.setup()

from store.models import EventSource, ShipmentEvent, Warehouse
from store.services.ups_client import (
    UpsClientError,
    fetch_world_id,
    notify_loaded,
    notify_ready,
)

from ack_manager import AckManager
from reconciliation import reconcile
from scheduler import Scheduler
from world_client import WorldClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

_WAREHOUSES_ENV = [
    (
        int(os.getenv("DEFAULT_WAREHOUSE_ID", "1")),
        int(os.getenv("DEFAULT_WAREHOUSE_X", "2")),
        int(os.getenv("DEFAULT_WAREHOUSE_Y", "4")),
    )
]


def _get_world_id():
    """Return the active world_id published by UPS, or None until UPS is ready."""
    try:
        return fetch_world_id()
    except UpsClientError as exc:
        logger.info("UPS world_id lookup failed: %s", exc)
    return None


def _persist_world_id(world_id: int) -> None:
    """Ensure warehouse rows match the connected world_id."""
    for wh_id, x, y in _WAREHOUSES_ENV:
        # Remove stale rows (no attached shipments) so they don't conflict.
        Warehouse.objects.filter(
            warehouse_id=wh_id
        ).exclude(
            world_id=world_id
        ).filter(
            shipments__isnull=True
        ).delete()
        # Create or update the canonical row for this world.
        Warehouse.objects.update_or_create(
            warehouse_id=wh_id,
            world_id=world_id,
            defaults={"x": x, "y": y},
        )


def main():
    scheduler = None
    ack_mgr = None
    client = None

    while True:
        try:
            world_id_to_use = _get_world_id()
            if world_id_to_use is None:
                logger.info("UPS world_id is not available yet; retrying in 5s")
                time.sleep(5)
                continue
            buffered_responses = []

            def dispatch_world_response(resp):
                if scheduler is None:
                    buffered_responses.append(resp)
                    return
                scheduler.on_world_response(resp)

            client = WorldClient(on_response=dispatch_world_response)
            world_id = client.connect(
                world_id=world_id_to_use,
                warehouses=_WAREHOUSES_ENV,
            )
            logger.info("World connected, world_id=%d", world_id)
            _persist_world_id(world_id)

            ack_mgr = AckManager(send_fn=client.send)
            ack_mgr.start()

            scheduler = Scheduler(
                world_client=client,
                ack_mgr=ack_mgr,
                ups_notify=ups_notify,
                world_id=world_id,
            )
            for resp in buffered_responses:
                scheduler.on_world_response(resp)
            buffered_responses.clear()
            reconcile(
                world_client=client,
                ack_mgr=ack_mgr,
                pending_packs=scheduler._pending_packs,
                pending_loads=scheduler._pending_loads,
                world_id=world_id,
            )
            scheduler.start()

            while client.is_connected:
                time.sleep(5)

        except ConnectionError as exc:
            err_msg = str(exc)
            if "is not available for amazon to connect" in err_msg:
                logger.warning("World %s no longer exists, waiting for UPS world refresh", world_id_to_use)
            else:
                logger.error("Connection error: %s — reconnecting in 10s", exc)
        except Exception as exc:
            logger.error("Unexpected error: %s — reconnecting in 10s", exc)
        finally:
            if scheduler:
                scheduler.stop()
            if ack_mgr:
                ack_mgr.stop()

        time.sleep(10)


def ups_notify(event: str, shipment_id: str) -> None:
    from store.models import Shipment
    try:
        shipment = Shipment.objects.select_related("order", "warehouse").prefetch_related(
            "items__product"
        ).get(shipment_id=shipment_id)
    except Shipment.DoesNotExist:
        logger.error("ups_notify: shipment %s not found", shipment_id)
        return

    try:
        if event == "packed":
            response = notify_ready(shipment)
            ShipmentEvent.objects.create(
                shipment=shipment,
                source=EventSource.SYSTEM,
                event_type="ups_notify_ready",
                world_id=shipment.world_id,
                status_snapshot=shipment.status,
                payload=response,
            )
            logger.info("notified UPS: ready shipment=%s", shipment_id)
        elif event == "loaded":
            response = notify_loaded(shipment)
            ShipmentEvent.objects.create(
                shipment=shipment,
                source=EventSource.SYSTEM,
                event_type="ups_notify_loaded",
                world_id=shipment.world_id,
                status_snapshot=shipment.status,
                payload=response,
            )
            logger.info("notified UPS: loaded shipment=%s", shipment_id)
        else:
            logger.warning("ups_notify: unknown event %s", event)
    except UpsClientError as exc:
        ShipmentEvent.objects.create(
            shipment=shipment,
            source=EventSource.SYSTEM,
            event_type=f"ups_notify_{event}_failed",
            world_id=shipment.world_id,
            status_snapshot=shipment.status,
            payload={
                "detail": str(exc),
                "status_code": exc.status_code,
                "response_body": exc.response_body,
            },
            error_message=str(exc),
        )
        logger.error("ups_notify %s failed for shipment %s: %s", event, shipment_id, exc)


if __name__ == "__main__":
    main()
