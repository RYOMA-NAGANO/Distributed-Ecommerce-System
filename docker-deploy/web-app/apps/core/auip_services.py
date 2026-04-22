from django.contrib.auth import get_user_model
from django.db import transaction

from apps.interop.services import amazon_client

from . import auip_states as S
from .models import Package, Truck
from .services import (
    NoAvailableTruckError,
    ShipmentNotFoundError,
    ShipmentStateError,
    ensure_trucks_initialized,
    resolve_world_package_id,
)

INTEROP_USER = "_amazon_interop"


def get_interop_user():
    return get_user_model().objects.get(username=INTEROP_USER)


def _get_pkg(shipment_id: str) -> Package | None:
    return Package.objects.filter(shipment_id=shipment_id).first()


@transaction.atomic
def auip_create_shipment(payload: dict) -> Package:
    shipment_id = payload["shipment_id"]
    world_id = int(payload["world_id"])
    if Package.objects.filter(shipment_id=shipment_id, world_id=world_id).exists():
        raise ValueError("duplicate_shipment")

    wh = payload["warehouse"]
    dest = payload["destination"]
    user = get_interop_user()
    wp = resolve_world_package_id(shipment_id, None)

    return Package.objects.create(
        shipment_id=shipment_id,
        world_id=world_id,
        amazon_order_id=str(payload.get("amazon_order_id") or ""),
        user=user,
        truck=None,
        warehouse_id=int(wh["id"]),
        warehouse_x=int(wh["x"]),
        warehouse_y=int(wh["y"]),
        dest_x=int(dest["x"]),
        dest_y=int(dest["y"]),
        items=payload.get("items"),
        world_package_id=wp,
        status=S.CREATED,
    )


@transaction.atomic
def auip_request_pickup(shipment_id: str, warehouse_id: int, world_id: int) -> Package:
    ensure_trucks_initialized()
    p = Package.objects.select_for_update().select_related("truck").filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if int(p.world_id) != int(world_id):
        raise ShipmentStateError("world_id mismatch.")
    if int(warehouse_id) != int(p.warehouse_id):
        raise ShipmentStateError("warehouse_id mismatch.")
    if p.status in S.PICKUP_BLOCKED:
        raise ShipmentStateError(f"pickup not allowed in state {p.status}")
    if p.truck_id is not None and p.status == S.TRUCK_EN_ROUTE:
        return p

    truck = (
        Truck.objects.select_for_update()
        .filter(truck_status=Truck.TruckStatus.IDLE)
        .order_by("truck_id")
        .first()
    )
    if truck is None:
        raise NoAvailableTruckError("No idle truck is available.")

    truck.truck_status = Truck.TruckStatus.TRAVELING
    truck.save(update_fields=["truck_status"])
    p.truck = truck
    p.status = S.TRUCK_EN_ROUTE
    p.save(update_fields=["truck", "status"])
    return p


@transaction.atomic
def auip_mark_ready(shipment_id: str, warehouse_id: int, world_id: int) -> Package:
    p = Package.objects.select_for_update().filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if int(p.world_id) != int(world_id):
        raise ShipmentStateError("world_id mismatch.")
    if int(warehouse_id) != int(p.warehouse_id):
        raise ShipmentStateError("warehouse_id mismatch.")
    if p.status == S.PACKED:
        return p
    if p.status in S.READY_BLOCKED:
        raise ShipmentStateError(f"ready not allowed in state {p.status}")
    if p.status != S.TRUCK_ARRIVED:
        raise ShipmentStateError(f"Shipment must be truck_arrived before ready: {p.status}")
    p.status = S.PACKED
    p.save(update_fields=["status"])
    return p


def auip_try_send_load_request_and_loading(package: Package) -> None:
    try:
        amazon_client.notify_load_request(package)
    except Exception:
        return
    with transaction.atomic():
        p = Package.objects.select_for_update().filter(shipment_id=package.shipment_id).first()
        if p and p.status == S.PACKED:
            p.status = S.LOADING
            p.save(update_fields=["status"])


@transaction.atomic
def auip_confirm_loaded(shipment_id: str, truck_id: int, warehouse_id: int, world_id: int) -> Package:
    p = Package.objects.select_for_update().filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if int(p.world_id) != int(world_id):
        raise ShipmentStateError("world_id mismatch.")
    if int(warehouse_id) != int(p.warehouse_id):
        raise ShipmentStateError("warehouse_id mismatch.")
    if p.truck_id is None or int(p.truck_id) != int(truck_id):
        raise ShipmentStateError("truck_id mismatch.")
    if p.status == S.LOADED:
        return p
    if p.status != S.LOADING:
        raise ShipmentStateError(f"loaded not allowed in state {p.status}")
    p.status = S.LOADED
    p.save(update_fields=["status"])
    if p.truck_id is not None:
        Truck.objects.filter(truck_id=p.truck_id).update(truck_status=Truck.TruckStatus.DELIVERING)
    return p


def auip_get_shipment_dict(shipment_id: str) -> dict:
    p = Package.objects.select_related("truck", "user").filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    return {
        "shipment_id": p.shipment_id,
        "status": p.status,
        "truck_id": p.truck_id,
        "warehouse_id": p.warehouse_id,
        "destination": {"x": p.dest_x, "y": p.dest_y},
        "ups_account": p.user.username,
        "world_id": int(p.world_id),
    }


@transaction.atomic
def auip_update_destination(shipment_id: str, x: int, y: int, reason: str) -> Package:
    p = Package.objects.select_for_update().filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if p.status in S.DESTINATION_BLOCKED:
        raise ShipmentStateError(f"destination update not allowed in state {p.status}")
    p.dest_x = int(x)
    p.dest_y = int(y)
    p.status = S.UPDATED
    p.save(update_fields=["dest_x", "dest_y", "status"])
    return p


@transaction.atomic
def auip_set_truck_arrived_for_truck(
    truck_id: int, location_x: int, location_y: int, pickup_seqnum: int | None = None
):
    qs = Package.objects.select_for_update().filter(
        truck_id=truck_id,
        status=S.TRUCK_EN_ROUTE,
        pickup_seqnum__isnull=False,
    )
    if pickup_seqnum is not None:
        qs = qs.filter(pickup_seqnum=int(pickup_seqnum))
    for package in qs:
        package.status = S.TRUCK_ARRIVED
        package.save(update_fields=["status"])
        try:
            amazon_client.notify_truck_arrived(package, location_x, location_y)
        except Exception:
            pass


def mark_package_loaded_for_delivery(shipment_id, restrict_to_user=None):
    """Dev/legacy: apply AUIP loaded using truck/warehouse/world from the row."""
    qs = Package.objects.filter(shipment_id=shipment_id)
    if restrict_to_user is not None:
        qs = qs.filter(user=restrict_to_user)
    p = qs.select_related("truck").first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if p.truck_id is None:
        raise ShipmentStateError("No truck assigned.")
    return auip_confirm_loaded(
        shipment_id,
        int(p.truck_id),
        int(p.warehouse_id),
        int(p.world_id),
    )


def create_package_with_assigned_truck(
    shipment_id,
    username,
    dest_x,
    dest_y,
    email="",
    warehouse_id=0,
    world_package_id=None,
    world_id=0,
    amazon_order_id="",
    warehouse_x=None,
    warehouse_y=None,
    items=None,
):
    """CLI / dev: AUIP create + reassign owner user + pickup."""
    if Package.objects.filter(shipment_id=shipment_id).exists():
        raise ValueError(f"Package {shipment_id} already exists.")
    wx = int(warehouse_x if warehouse_x is not None else 0)
    wy = int(warehouse_y if warehouse_y is not None else 0)
    payload = {
        "shipment_id": shipment_id,
        "world_id": int(world_id),
        "amazon_order_id": amazon_order_id or "CLI",
        "warehouse": {"id": int(warehouse_id), "x": wx, "y": wy},
        "destination": {"x": int(dest_x), "y": int(dest_y)},
        "items": items,
    }
    p = auip_create_shipment(payload)
    user_model = get_user_model()
    u, created = user_model.objects.get_or_create(username=username, defaults={"email": email or ""})
    if created:
        u.set_unusable_password()
        u.save(update_fields=["password"])
    elif email and not u.email:
        u.email = email
        u.save(update_fields=["email"])
    p.user = u
    update_fields = ["user"]
    if world_package_id is not None:
        p.world_package_id = int(world_package_id)
        update_fields.append("world_package_id")
    p.save(update_fields=update_fields)
    return auip_request_pickup(shipment_id, int(warehouse_id), int(world_id))
