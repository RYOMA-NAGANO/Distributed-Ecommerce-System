import logging
import time

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When

from apps.interop.services import amazon_client

from . import auip_states as S
from .models import DestinationUpdate, Package, PositionUpdate, StatusUpdate, Truck
from .services import (
    ShipmentNotFoundError,
    ShipmentStateError,
    resolve_world_package_id,
)

INTEROP_USER = "_amazon_interop"
logger = logging.getLogger(__name__)
_PICKUP_ELIGIBLE_TRUCK_STATUSES = (
    Truck.TruckStatus.IDLE,
    Truck.TruckStatus.ARRIVE_WAREHOUSE,
    Truck.TruckStatus.DELIVERING,
)
_ACTIVE_PACKAGE_STATUSES = (
    S.TRUCK_EN_ROUTE,
    S.TRUCK_ARRIVED,
    S.LOADING,
    S.LOADED,
    S.OUT_FOR_DELIVERY,
)


def _pickup_status_ordering(qs):
    return qs.annotate(
        _pickup_priority=Case(
            When(truck_status=Truck.TruckStatus.IDLE, then=Value(0)),
            When(truck_status=Truck.TruckStatus.ARRIVE_WAREHOUSE, then=Value(1)),
            When(truck_status=Truck.TruckStatus.DELIVERING, then=Value(2)),
            When(truck_status=Truck.TruckStatus.LOADING, then=Value(3)),
            When(truck_status=Truck.TruckStatus.TRAVELING, then=Value(4)),
            default=Value(5),
            output_field=IntegerField(),
        )
    )


def get_interop_user():
    return get_user_model().objects.get(username=INTEROP_USER)


def _get_pkg(shipment_id: str) -> Package | None:
    return Package.objects.filter(shipment_id=shipment_id).first()


def _record_destination_update(package: Package, x: int, y: int) -> None:
    DestinationUpdate.objects.create(
        shipment=package,
        x=int(x),
        y=int(y),
        update_time=int(time.time()),
    )


def _record_position_update(package: Package, x: int, y: int) -> None:
    PositionUpdate.objects.create(
        shipment=package,
        x=int(x),
        y=int(y),
        update_time=int(time.time()),
    )


def record_status_update(package: Package, status: str, *, update_time: int | None = None) -> None:
    timestamp = int(time.time()) if update_time is None else int(update_time)
    latest = (
        StatusUpdate.objects.filter(shipment=package)
        .order_by("-update_time", "-id")
        .first()
    )
    if latest and latest.status == status:
        return
    StatusUpdate.objects.create(
        shipment=package,
        status=str(status),
        update_time=timestamp,
    )


def _ensure_unique_world_package_id(*, shipment_id: str, world_id: int, world_package_id: int) -> None:
    conflict = (
        Package.objects.filter(world_id=int(world_id), world_package_id=int(world_package_id))
        .exclude(shipment_id=shipment_id)
        .exists()
    )
    if conflict:
        raise ValueError("duplicate_world_package_id")


def _choose_truck_for_pickup(*, exclude_ids: set[int] | None = None) -> Truck | None:
    qs = Truck.objects.select_for_update().filter(
        truck_status__in=_PICKUP_ELIGIBLE_TRUCK_STATUSES
    )
    if exclude_ids:
        qs = qs.exclude(truck_id__in=exclude_ids)
    return _pickup_status_ordering(qs).order_by("_pickup_priority", "truck_id").first()

def _choose_truck_for_queue(*, exclude_ids: set[int] | None = None) -> Truck | None:
    """
    When all trucks are busy, queue on an existing known truck.
    Do not invent new truck ids mid-session; World only accepts known trucks.
    """
    qs = Truck.objects.select_for_update().exclude(truck_status=Truck.TruckStatus.INVALID)
    if exclude_ids:
        qs = qs.exclude(truck_id__in=exclude_ids)
    return _pickup_status_ordering(qs).order_by("_pickup_priority", "truck_id").first()


@transaction.atomic
def auip_rebalance_waiting_pickups(limit: int = 30, world_id: int | None = None) -> int:
    """
    Reassign waiting pickup jobs to idle/arrived trucks if their current truck
    is not currently pickup-friendly.
    """
    waiting = Package.objects.select_for_update().filter(
        status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
        pickup_seqnum__isnull=True,
        truck__isnull=False,
    )
    if world_id is not None:
        waiting = waiting.filter(world_id=int(world_id))

    shipment_ids = list(waiting.order_by("shipment_id").values_list("shipment_id", flat=True)[:limit])
    if not shipment_ids:
        return 0

    reassigned = 0
    for shipment_id in shipment_ids:
        package = (
            Package.objects.select_for_update()
            .filter(shipment_id=shipment_id, truck__isnull=False)
            .only("shipment_id", "truck_id")
            .first()
        )
        if package is None or package.truck_id is None:
            continue
        current_truck = Truck.objects.filter(truck_id=int(package.truck_id)).only(
            "truck_id",
            "truck_status",
        ).first()
        if current_truck is None:
            continue
        if current_truck.truck_status in (
            Truck.TruckStatus.IDLE,
            Truck.TruckStatus.ARRIVE_WAREHOUSE,
        ):
            continue

        better = _choose_truck_for_pickup(exclude_ids={int(current_truck.truck_id)})
        if better is None or better.truck_status not in (
            Truck.TruckStatus.IDLE,
            Truck.TruckStatus.ARRIVE_WAREHOUSE,
        ):
            continue

        package.truck = better
        package.save(update_fields=["truck"])
        reassigned += 1

    if reassigned:
        logger.info("rebalanced %d waiting pickups onto idle/arrived trucks", reassigned)
    return reassigned


@transaction.atomic
def auip_assign_unassigned_pickups(limit: int = 30, world_id: int | None = None) -> int:
    """
    Bind waiting pickup jobs that currently have no truck to a known truck.
    """
    waiting = Package.objects.select_for_update().filter(
        status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
        pickup_seqnum__isnull=True,
        truck__isnull=True,
    )
    if world_id is not None:
        waiting = waiting.filter(world_id=int(world_id))

    shipment_ids = list(waiting.order_by("shipment_id").values_list("shipment_id", flat=True)[:limit])
    if not shipment_ids:
        return 0

    assigned = 0
    for shipment_id in shipment_ids:
        package = (
            Package.objects.select_for_update()
            .filter(
                shipment_id=shipment_id,
                status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
                pickup_seqnum__isnull=True,
                truck__isnull=True,
            )
            .only("shipment_id")
            .first()
        )
        if package is None:
            continue

        truck = _choose_truck_for_pickup()
        if truck is None:
            truck = _choose_truck_for_queue()
        if truck is None:
            continue

        if truck.truck_status in _PICKUP_ELIGIBLE_TRUCK_STATUSES:
            truck.truck_status = Truck.TruckStatus.TRAVELING
            truck.save(update_fields=["truck_status"])

        package.truck = truck
        package.save(update_fields=["truck"])
        assigned += 1

    if assigned:
        logger.info("assigned %d waiting pickups to trucks", assigned)
    return assigned


def _release_truck_if_orphaned(truck_id: int | None, *, exclude_shipment_id: str | None = None) -> None:
    if not truck_id:
        return
    active = Package.objects.filter(
        truck_id=truck_id,
        status__in=_ACTIVE_PACKAGE_STATUSES,
    )
    if exclude_shipment_id:
        active = active.exclude(shipment_id=exclude_shipment_id)
    if not active.exists():
        truck = Truck.objects.filter(truck_id=truck_id).only("truck_status").first()
        if truck and truck.truck_status != Truck.TruckStatus.INVALID:
            Truck.objects.filter(truck_id=truck_id).update(truck_status=Truck.TruckStatus.IDLE)


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
    _ensure_unique_world_package_id(
        shipment_id=shipment_id,
        world_id=world_id,
        world_package_id=int(wp),
    )

    package = Package.objects.create(
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
    _record_destination_update(package, package.dest_x, package.dest_y)
    record_status_update(package, package.status)
    return package


@transaction.atomic
def auip_request_pickup(shipment_id: str, warehouse_id: int, world_id: int) -> Package:
    # Avoid FOR UPDATE on an outer join (truck is nullable), which PostgreSQL rejects.
    p = Package.objects.select_for_update().filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if int(p.world_id) != int(world_id):
        raise ShipmentStateError("world_id mismatch.")
    if int(warehouse_id) != int(p.warehouse_id):
        raise ShipmentStateError("warehouse_id mismatch.")
    if p.status in S.PICKUP_BLOCKED:
        raise ShipmentStateError(f"pickup not allowed in state {p.status}")
    # If pickup command is already in-flight, keep waiting.
    if p.status == S.TRUCK_EN_ROUTE and p.pickup_seqnum is not None:
        return p

    # Pickup dispatch chooses truck at send-time in daemon loop.
    previous_status = p.status
    p.truck = None
    p.status = S.TRUCK_EN_ROUTE
    p.pickup_seqnum = None
    p.save(update_fields=["truck", "status", "pickup_seqnum"])
    if p.status != previous_status:
        record_status_update(p, p.status)
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
    if p.status not in (S.CREATED, S.TRUCK_EN_ROUTE, S.TRUCK_ARRIVED):
        raise ShipmentStateError(f"ready not allowed in state {p.status}")
    should_record_warehouse_position = not PositionUpdate.objects.filter(
        shipment=p,
        x=int(p.warehouse_x),
        y=int(p.warehouse_y),
    ).exists()
    # If truck is already at warehouse, keep that stronger state.
    previous_status = p.status
    if p.status == S.TRUCK_ARRIVED:
        p.status = S.TRUCK_ARRIVED
    else:
        p.status = S.PACKED
    p.save(update_fields=["status"])
    if p.status != previous_status:
        record_status_update(p, p.status)
    if should_record_warehouse_position:
        _record_position_update(p, p.warehouse_x, p.warehouse_y)
    return p


def auip_try_send_load_request_and_loading(package: Package) -> None:
    try:
        amazon_client.notify_load_request(package)
    except Exception:
        return
    with transaction.atomic():
        p = Package.objects.select_for_update().filter(shipment_id=package.shipment_id).first()
        if p and p.status in (S.PACKED, S.TRUCK_ARRIVED):
            previous_status = p.status
            p.status = S.LOADING
            p.save(update_fields=["status"])
            if p.status != previous_status:
                record_status_update(p, p.status)


def auip_try_send_load_request_when_possible(shipment_id: str) -> bool:
    package = (
        Package.objects.select_related("truck")
        .filter(shipment_id=shipment_id)
        .first()
    )
    if package is None:
        return False
    if package.status not in (S.PACKED, S.TRUCK_ARRIVED):
        return False
    if package.truck_id is None:
        return False
    if package.truck is None or package.truck.truck_status not in (
        Truck.TruckStatus.ARRIVE_WAREHOUSE,
        Truck.TruckStatus.LOADING,
    ):
        return False

    auip_try_send_load_request_and_loading(package)
    refreshed = Package.objects.only("status").filter(shipment_id=shipment_id).first()
    return bool(refreshed and refreshed.status == S.LOADING)


def auip_retry_pending_load_requests(limit: int = 20, world_id: int | None = None) -> None:
    qs = Package.objects.select_related("truck").filter(
        status__in=[S.PACKED, S.TRUCK_ARRIVED],
        truck__truck_status__in=[
            Truck.TruckStatus.ARRIVE_WAREHOUSE,
            Truck.TruckStatus.LOADING,
        ],
    )
    if world_id is not None:
        qs = qs.filter(world_id=int(world_id))
    shipment_ids = list(qs.values_list("shipment_id", flat=True)[:limit])
    for shipment_id in shipment_ids:
        auip_try_send_load_request_when_possible(shipment_id)


@transaction.atomic
def auip_recover_stale_pickup_requests(limit: int = 30, world_id: int | None = None) -> int:
    """
    Self-heal rows where pickup_seqnum remained set even though the truck is no
    longer traveling to a warehouse. Those rows are otherwise skipped forever.
    """
    qs = Package.objects.select_for_update().filter(
        status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
        pickup_seqnum__isnull=False,
    )
    if world_id is not None:
        qs = qs.filter(world_id=int(world_id))

    shipment_ids = list(qs.order_by("shipment_id").values_list("shipment_id", flat=True)[:limit])
    if not shipment_ids:
        return 0

    cleared = 0
    for shipment_id in shipment_ids:
        package = (
            Package.objects.select_for_update()
            .filter(
                shipment_id=shipment_id,
                status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
                pickup_seqnum__isnull=False,
            )
            .only("shipment_id", "truck_id", "pickup_seqnum")
            .first()
        )
        if package is None:
            continue
        if package.truck_id is not None:
            truck = Truck.objects.filter(truck_id=int(package.truck_id)).only("truck_status").first()
            if truck is not None and truck.truck_status == Truck.TruckStatus.TRAVELING:
                continue
        package.pickup_seqnum = None
        package.save(update_fields=["pickup_seqnum"])
        cleared += 1

    if cleared:
        logger.info("cleared %d stale pickup seqnums", cleared)
    return cleared


@transaction.atomic
def auip_recover_stuck_loading(limit: int = 20, world_id: int | None = None) -> int:
    """
    Self-heal UPS rows waiting for Amazon loading after missed/failed cross-service updates.
    If the truck is still at the warehouse, retry loading from TRUCK_ARRIVED.
    If the truck has already left or gone idle, requeue the package for pickup.
    """
    qs = Package.objects.select_for_update().filter(status__in=[S.LOADING, S.TRUCK_ARRIVED])
    if world_id is not None:
        qs = qs.filter(world_id=int(world_id))
    ids = list(qs.values_list("shipment_id", flat=True)[:limit])
    if not ids:
        return 0
    updated = 0
    for package in Package.objects.select_for_update().filter(
        shipment_id__in=ids,
        status__in=[S.LOADING, S.TRUCK_ARRIVED],
    ):
        previous_status = package.status
        update_fields = []
        truck_status = None
        if package.truck_id is not None:
            truck_status = (
                Truck.objects.filter(truck_id=int(package.truck_id))
                .values_list("truck_status", flat=True)
                .first()
            )

        if truck_status in (
            Truck.TruckStatus.ARRIVE_WAREHOUSE,
            Truck.TruckStatus.LOADING,
        ):
            package.status = S.TRUCK_ARRIVED
            update_fields.append("status")
        else:
            package.status = S.PACKED
            update_fields.append("status")
            if package.truck_id is not None:
                package.truck = None
                update_fields.append("truck")
            if package.pickup_seqnum is not None:
                package.pickup_seqnum = None
                update_fields.append("pickup_seqnum")

        package.save(update_fields=update_fields)
        if package.status != previous_status:
            record_status_update(package, package.status)
            updated += 1
    if updated:
        logger.info("recovered %d stuck warehouse-loading packages", updated)
    return int(updated)


def auip_reconcile_truck_arrivals(limit: int = 20, world_id: int | None = None) -> None:
    """
    Self-heal cases where world truck already reached warehouse (LOADING),
    but package still remains truck_en_route due missed/mismatched completion handling.
    """
    qs = Package.objects.select_related("truck").filter(
        status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
        truck__truck_status__in=[
            Truck.TruckStatus.ARRIVE_WAREHOUSE,
            Truck.TruckStatus.LOADING,
        ],
    )
    if world_id is not None:
        qs = qs.filter(world_id=int(world_id))
    candidates = list(
        qs.values("truck_id", "warehouse_x", "warehouse_y").distinct()[:limit]
    )
    for row in candidates:
        auip_set_truck_arrived_for_truck(
            int(row["truck_id"]),
            int(row["warehouse_x"]),
            int(row["warehouse_y"]),
            pickup_seqnum=None,
        )


@transaction.atomic
def auip_requeue_interrupted_deliveries_for_truck(
    truck_id: int,
    world_id: int | None = None,
) -> int:
    """
    If a pickup interrupts an in-flight delivery route, mark those deliveries as
    pending resend by clearing delivery_seqnum while keeping OUT_FOR_DELIVERY.
    """
    qs = Package.objects.select_for_update().filter(
        truck_id=int(truck_id),
        status=S.OUT_FOR_DELIVERY,
        delivery_seqnum__isnull=False,
    )
    if world_id is not None:
        qs = qs.filter(world_id=int(world_id))

    updated = qs.update(delivery_seqnum=None)
    if updated:
        logger.info(
            "requeued %d interrupted deliveries for truck=%s",
            updated,
            truck_id,
        )
    return int(updated)


@transaction.atomic
def auip_rotate_pickup_truck(shipment_id: str) -> tuple[int | None, int | None]:
    """
    On pickup dispatch error, clear previously bound truck and pickup seq.
    Next pickup send attempt will choose a legal dispatchable truck from DB.
    Returns (old_truck_id, new_truck_id).
    """
    package = Package.objects.select_for_update().filter(shipment_id=shipment_id).first()
    if package is None:
        return None, None

    old_truck_id = package.truck_id

    previous_status = package.status
    package.truck = None
    package.pickup_seqnum = None
    package.status = S.TRUCK_EN_ROUTE
    package.save(update_fields=["truck", "pickup_seqnum", "status"])
    if package.status != previous_status:
        record_status_update(package, package.status)

    _release_truck_if_orphaned(old_truck_id, exclude_shipment_id=shipment_id)
    return old_truck_id, None


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
    if p.status not in (S.LOADING, S.TRUCK_ARRIVED, S.PACKED):
        raise ShipmentStateError(f"loaded not allowed in state {p.status}")
    previous_status = p.status
    p.status = S.LOADED
    p.save(update_fields=["status"])
    if p.status != previous_status:
        record_status_update(p, p.status)
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
    previous_status = p.status
    p.dest_x = int(x)
    p.dest_y = int(y)
    p.status = S.UPDATED
    p.save(update_fields=["dest_x", "dest_y", "status"])
    if p.status != previous_status:
        record_status_update(p, p.status)
    _record_destination_update(p, p.dest_x, p.dest_y)
    return p


@transaction.atomic
def update_destination_for_owner(shipment_id: str, user, x: int, y: int) -> Package:
    p = Package.objects.select_for_update().filter(shipment_id=shipment_id).first()
    if p is None:
        raise ShipmentNotFoundError("Unknown shipment_id.")
    if p.user_id != user.id:
        raise ShipmentStateError("Only the package owner can update the destination.")
    if p.status == S.DELIVERED:
        raise ShipmentStateError("Delivered packages cannot be redirected.")

    update_fields = ["dest_x", "dest_y"]
    p.dest_x = int(x)
    p.dest_y = int(y)

    if p.status in (S.LOADED, S.OUT_FOR_DELIVERY):
        if p.truck_id is None:
            raise ShipmentStateError("Loaded package has no assigned truck.")
        if p.world_package_id is None:
            raise ShipmentStateError("Loaded package has no World package id.")
        # Clearing delivery_seqnum puts this package back in the daemon's
        # delivery retry pool, so the current truck receives a fresh UGoDeliver.
        p.delivery_seqnum = None
        update_fields.append("delivery_seqnum")

    p.save(update_fields=update_fields)
    _record_destination_update(p, p.dest_x, p.dest_y)
    return p


@transaction.atomic
def auip_set_truck_arrived_for_truck(
    truck_id: int, location_x: int, location_y: int, pickup_seqnum: int | None = None
):
    base_qs = Package.objects.select_for_update().filter(
        truck_id=truck_id,
        warehouse_x=int(location_x),
        warehouse_y=int(location_y),
        status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
    )
    qs = base_qs
    if pickup_seqnum is not None:
        by_seq_qs = base_qs.filter(pickup_seqnum=int(pickup_seqnum))
        if by_seq_qs.exists():
            qs = by_seq_qs
        else:
            # World completion seqnum is not guaranteed to equal command seqnum.
            logger.warning(
                "pickup completion seqnum mismatch for truck=%s seq=%s; "
                "falling back to truck-level matching",
                truck_id,
                pickup_seqnum,
            )

    updated_count = 0
    for package in qs:
        previous_status = package.status
        update_fields = []
        if package.status in (S.TRUCK_EN_ROUTE, S.PACKED):
            package.status = S.TRUCK_ARRIVED
            update_fields.append("status")
        if package.pickup_seqnum is not None:
            package.pickup_seqnum = None
            update_fields.append("pickup_seqnum")
        if update_fields:
            package.save(update_fields=update_fields)
            if package.status != previous_status:
                record_status_update(package, package.status)
        updated_count += 1
        try:
            amazon_client.notify_truck_arrived(package, location_x, location_y)
        except Exception as exc:
            logger.warning(
                "notify_truck_arrived failed for shipment=%s truck=%s: %s",
                package.shipment_id,
                truck_id,
                exc,
            )
        if package.status == S.TRUCK_ARRIVED:
            auip_try_send_load_request_when_possible(package.shipment_id)
    return updated_count


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
        _ensure_unique_world_package_id(
            shipment_id=shipment_id,
            world_id=int(world_id),
            world_package_id=int(world_package_id),
        )
        p.world_package_id = int(world_package_id)
        update_fields.append("world_package_id")
    p.save(update_fields=update_fields)
    return auip_request_pickup(shipment_id, int(warehouse_id), int(world_id))
