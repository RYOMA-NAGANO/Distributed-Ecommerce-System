import os
import random
import time

from django.db import transaction

from store.models import (
    EventSource,
    Order,
    Product,
    Shipment,
    ShipmentEvent,
    ShipmentItem,
    ShipmentStatus,
    Warehouse,
)
from store.services.ups_client import (
    UpsClientError,
    create_shipment,
    fetch_world_id,
    request_pickup,
)

DEFAULT_WAREHOUSE_ID = int(os.getenv("DEFAULT_WAREHOUSE_ID", "1"))
DEFAULT_WAREHOUSE_X = int(os.getenv("DEFAULT_WAREHOUSE_X", "2"))
DEFAULT_WAREHOUSE_Y = int(os.getenv("DEFAULT_WAREHOUSE_Y", "4"))
WORLD_DESCRIPTION_MAX_LEN = 50


def create_order_from_product(
    *,
    product_data: dict,
    quantity: int,
    destination_x: int,
    destination_y: int,
    ups_account: str = "",
):
    warehouse = _get_default_warehouse()
    shipment_id = _generate_shipment_id(world_id=warehouse.world_id)
    amazon_order_id = f"ORD-{shipment_id}"

    product, _ = Product.objects.get_or_create(
        product_id=int(product_data["product_id"]),
        defaults={
            "name": product_data.get("name", ""),
            "description": product_data["description"],
            "price": product_data.get("price", "0.00"),
            "category": product_data.get("category", ""),
            "badge": product_data.get("badge", ""),
            "image_url": product_data.get("image_url", ""),
        },
    )

    with transaction.atomic():
        order = Order.objects.create(
            amazon_order_id=amazon_order_id,
            requested_destination_x=destination_x,
            requested_destination_y=destination_y,
            ups_account=ups_account,
        )

        shipment = Shipment.objects.create(
            order=order,
            warehouse=warehouse,
            world_id=warehouse.world_id,
            shipment_id=shipment_id,
            tracking_number=shipment_id,
            status=ShipmentStatus.CREATED,
            destination_x=destination_x,
            destination_y=destination_y,
        )

        ShipmentItem.objects.create(
            shipment=shipment,
            product=product,
            quantity=quantity,
            description_snapshot=product.description[:WORLD_DESCRIPTION_MAX_LEN],
        )

        ShipmentEvent.objects.create(
            shipment=shipment,
            source=EventSource.WEB,
            event_type="shipment_created",
            world_id=warehouse.world_id,
            status_snapshot=ShipmentStatus.CREATED,
            payload={
                "amazon_order_id": amazon_order_id,
                "shipment_id": shipment_id,
                "product_id": product.product_id,
                "quantity": quantity,
                "destination_x": destination_x,
                "destination_y": destination_y,
                "ups_account": ups_account,
            },
        )

        transaction.on_commit(lambda: _sync_shipment_to_ups(shipment.id))

    return order, shipment


def _get_default_warehouse() -> Warehouse:
    configured_world_id = int(os.getenv("WORLD_ID", "0") or "0")

    if configured_world_id:
        world_id = configured_world_id
        warehouse, _ = Warehouse.objects.get_or_create(
            world_id=world_id,
            warehouse_id=DEFAULT_WAREHOUSE_ID,
            defaults={
                "x": DEFAULT_WAREHOUSE_X,
                "y": DEFAULT_WAREHOUSE_Y,
            },
        )
        return warehouse

    try:
        world_id = fetch_world_id()
        warehouse, _ = Warehouse.objects.get_or_create(
            world_id=world_id,
            warehouse_id=DEFAULT_WAREHOUSE_ID,
            defaults={
                "x": DEFAULT_WAREHOUSE_X,
                "y": DEFAULT_WAREHOUSE_Y,
            },
        )
        return warehouse
    except UpsClientError:
        pass

    existing = Warehouse.objects.filter(
        warehouse_id=DEFAULT_WAREHOUSE_ID,
        world_id__gt=0,
    ).order_by("-id").first()
    if existing:
        return existing

    existing = Warehouse.objects.order_by("-id").first()
    if existing:
        return existing

    raise UpsClientError("No usable world_id is available from UPS and no warehouse is persisted locally.")


def _generate_shipment_id(*, world_id: int) -> str:
    while True:
        candidate = f"{int(time.time() * 1000)}{random.randint(1000, 9999)}"
        if not Shipment.objects.filter(world_id=world_id, shipment_id=candidate).exists():
            return candidate


def _sync_shipment_to_ups(shipment_pk: int) -> None:
    shipment = (
        Shipment.objects.select_related("order", "warehouse")
        .prefetch_related("items__product")
        .get(pk=shipment_pk)
    )

    try:
        create_response = create_shipment(shipment)
        pickup_response = request_pickup(shipment)

        tracking_number = create_response.get("tracking_number") or shipment.tracking_number
        if tracking_number and tracking_number != shipment.tracking_number:
            Shipment.objects.filter(pk=shipment.pk).update(tracking_number=tracking_number)
            shipment.tracking_number = tracking_number

        ShipmentEvent.objects.create(
            shipment=shipment,
            source=EventSource.WEB,
            event_type="ups_create_shipment",
            world_id=shipment.world_id,
            status_snapshot=shipment.status,
            payload=create_response,
        )
        ShipmentEvent.objects.create(
            shipment=shipment,
            source=EventSource.WEB,
            event_type="ups_request_pickup",
            world_id=shipment.world_id,
            status_snapshot=shipment.status,
            payload=pickup_response,
        )
    except UpsClientError as exc:
        ShipmentEvent.objects.create(
            shipment=shipment,
            source=EventSource.WEB,
            event_type="ups_sync_failed",
            world_id=shipment.world_id,
            status_snapshot=shipment.status,
            payload={
                "detail": str(exc),
                "status_code": exc.status_code,
                "response_body": exc.response_body,
            },
            error_message=str(exc),
        )
