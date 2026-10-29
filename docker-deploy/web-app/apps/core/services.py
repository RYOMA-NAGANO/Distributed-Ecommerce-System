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
