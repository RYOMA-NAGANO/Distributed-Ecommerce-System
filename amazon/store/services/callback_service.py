from dataclasses import dataclass

from django.db import transaction

from store.models import EventSource, Shipment, ShipmentEvent, ShipmentStatus


class CallbackBadRequest(Exception):
    pass


class CallbackConflict(Exception):
    pass


@dataclass
class CallbackResult:
    shipment_id: str
    status: str
    world_id: int


def handle_truck_arrived(payload: dict) -> CallbackResult:
    shipment = _get_shipment(payload)
    warehouse_id = _required_int(payload, "warehouse_id")
    truck_id = _required_int(payload, "truck_id")

    if shipment.warehouse.warehouse_id != warehouse_id:
        raise CallbackConflict("warehouse_id does not match shipment")
    if shipment.status in (
        ShipmentStatus.LOADED,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
        ShipmentStatus.CANCELED,
    ):
        raise CallbackConflict("shipment can no longer accept truck arrival")

    with transaction.atomic():
        locked = Shipment.objects.select_for_update().get(pk=shipment.pk)
        if locked.truck_id is not None and locked.truck_id != truck_id:
            raise CallbackConflict("truck_id does not match existing shipment truck")

        locked.truck_id = truck_id
        if locked.status == ShipmentStatus.PACKED:
            locked.status = ShipmentStatus.TRUCK_ARRIVED
        locked.save(update_fields=["truck_id", "status", "updated_at"])
        _record_event(locked, "truck_arrived", payload)

        return CallbackResult(
            shipment_id=locked.shipment_id,
            status=locked.status,
            world_id=locked.world_id,
        )


def handle_load_request(payload: dict) -> CallbackResult:
    shipment = _get_shipment(payload)
    warehouse_id = _required_int(payload, "warehouse_id")
    truck_id = _required_int(payload, "truck_id")

    if shipment.warehouse.warehouse_id != warehouse_id:
        raise CallbackConflict("warehouse_id does not match shipment")
    if shipment.truck_id is not None and shipment.truck_id != truck_id:
        raise CallbackConflict("truck_id does not match shipment")
    if shipment.status == ShipmentStatus.CANCELED:
        raise CallbackConflict("shipment can no longer accept load requests")

    with transaction.atomic():
        locked = Shipment.objects.select_for_update().get(pk=shipment.pk)
        if locked.truck_id is None:
            raise CallbackConflict("truck has not arrived for this shipment")
        if locked.truck_id != truck_id:
            raise CallbackConflict("truck_id does not match shipment")
        if locked.status not in (
            ShipmentStatus.PACKED,
            ShipmentStatus.TRUCK_ARRIVED,
            ShipmentStatus.LOADING,
            ShipmentStatus.LOADED,
            ShipmentStatus.OUT_FOR_DELIVERY,
            ShipmentStatus.DELIVERED,
        ):
            raise CallbackConflict("shipment is not packed or truck has not arrived")

        if locked.status in (ShipmentStatus.PACKED, ShipmentStatus.TRUCK_ARRIVED):
            locked.status = ShipmentStatus.LOADING

        locked.save(update_fields=["truck_id", "status", "updated_at"])
        _record_event(locked, "load_request", payload)

        return CallbackResult(
            shipment_id=locked.shipment_id,
            status=locked.status,
            world_id=locked.world_id,
        )


def handle_out_for_delivery(payload: dict) -> CallbackResult:
    shipment = _get_shipment(payload)
    truck_id = _required_int(payload, "truck_id")
    destination = payload.get("destination") or {}
    destination_x = destination.get("x")
    destination_y = destination.get("y")

    with transaction.atomic():
        locked = Shipment.objects.select_for_update().get(pk=shipment.pk)
        if locked.truck_id is not None and locked.truck_id != truck_id:
            raise CallbackConflict("truck_id does not match shipment")
        if locked.status == ShipmentStatus.DELIVERED:
            return CallbackResult(
                shipment_id=locked.shipment_id,
                status=locked.status,
                world_id=locked.world_id,
            )
        if locked.status not in (
            ShipmentStatus.LOADED,
            ShipmentStatus.OUT_FOR_DELIVERY,
        ):
            raise CallbackConflict("shipment is not loaded yet")

        locked.truck_id = truck_id
        locked.status = ShipmentStatus.OUT_FOR_DELIVERY
        if destination_x is not None:
            locked.destination_x = int(destination_x)
        if destination_y is not None:
            locked.destination_y = int(destination_y)
        locked.save(
            update_fields=[
                "truck_id",
                "status",
                "destination_x",
                "destination_y",
                "updated_at",
            ]
        )
        _record_event(locked, "out_for_delivery", payload)

        return CallbackResult(
            shipment_id=locked.shipment_id,
            status=locked.status,
            world_id=locked.world_id,
        )


def handle_delivered(payload: dict) -> CallbackResult:
    shipment = _get_shipment(payload)
    truck_id = _required_int(payload, "truck_id")

    with transaction.atomic():
        locked = Shipment.objects.select_for_update().get(pk=shipment.pk)
        if locked.truck_id is not None and locked.truck_id != truck_id:
            raise CallbackConflict("truck_id does not match shipment")
        if locked.status == ShipmentStatus.DELIVERED:
            return CallbackResult(
                shipment_id=locked.shipment_id,
                status=locked.status,
                world_id=locked.world_id,
            )
        if locked.status not in (
            ShipmentStatus.LOADED,
            ShipmentStatus.OUT_FOR_DELIVERY,
        ):
            raise CallbackConflict("shipment is not out for delivery yet")

        locked.truck_id = truck_id
        locked.status = ShipmentStatus.DELIVERED
        locked.save(update_fields=["truck_id", "status", "updated_at"])
        _record_event(locked, "delivered", payload)

        return CallbackResult(
            shipment_id=locked.shipment_id,
            status=locked.status,
            world_id=locked.world_id,
        )


def _get_shipment(payload: dict) -> Shipment:
    shipment_id = payload.get("shipment_id")
    if not shipment_id:
        raise CallbackBadRequest("shipment_id is required")

    world_id = payload.get("world_id")
    if world_id is not None:
        shipment = Shipment.objects.filter(
            shipment_id=str(shipment_id),
            world_id=int(world_id),
        ).select_related("warehouse").first()
    else:
        shipment = Shipment.objects.filter(
            shipment_id=str(shipment_id),
        ).select_related("warehouse").first()

    if shipment is None:
        raise CallbackBadRequest("shipment not found")

    return shipment


def _required_int(payload: dict, field: str) -> int:
    value = payload.get(field)
    if value is None:
        raise CallbackBadRequest(f"{field} is required")
    return int(value)


def _record_event(shipment: Shipment, event_type: str, payload: dict) -> None:
    if event_type == "load_request":
        if ShipmentEvent.objects.filter(
            shipment=shipment,
            event_type="load_request",
        ).exists():
            return

    ShipmentEvent.objects.create(
        shipment=shipment,
        source=EventSource.UPS,
        event_type=event_type,
        world_id=shipment.world_id,
        status_snapshot=shipment.status,
        payload=payload,
    )
