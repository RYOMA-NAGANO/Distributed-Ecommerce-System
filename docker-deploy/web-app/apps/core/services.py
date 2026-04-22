import json

from django.conf import settings

from .models import Truck


class NoAvailableTruckError(Exception):
    pass


class ShipmentNotFoundError(Exception):
    pass


class ShipmentStateError(Exception):
    pass


def resolve_world_package_id(shipment_id, world_package_id):
    if world_package_id is not None:
        return int(world_package_id)

    if isinstance(shipment_id, str) and shipment_id.isdigit():
        return int(shipment_id)

    digits = "".join(c for c in str(shipment_id) if c.isdigit())
    if digits:
        return int(digits)

    raise ValueError(
        "world_package_id is required when shipment_id has no digits to derive World package id."
    )


def ensure_trucks_initialized():
    configured_trucks = json.loads(settings.UPS_TRUCKS)
    for truck in configured_trucks:
        Truck.objects.get_or_create(
            truck_id=truck["id"],
            defaults={"truck_status": Truck.TruckStatus.IDLE},
        )


def create_package_with_assigned_truck(*args, **kwargs):
    from . import auip_services

    return auip_services.create_package_with_assigned_truck(*args, **kwargs)


def mark_package_loaded_for_delivery(*args, **kwargs):
    from . import auip_services

    return auip_services.mark_package_loaded_for_delivery(*args, **kwargs)
