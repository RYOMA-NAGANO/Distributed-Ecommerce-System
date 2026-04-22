from store.models import ShipmentStatus


TIMELINE_LABELS = [
    "Created",
    "Packing",
    "Truck Ready",
    "Loaded",
    "Delivered",
]

STATUS_RANKS = {
    ShipmentStatus.CREATED: 0,
    ShipmentStatus.PACKING: 1,
    ShipmentStatus.PACKED: 1,
    ShipmentStatus.TRUCK_EN_ROUTE: 2,
    ShipmentStatus.TRUCK_ARRIVED: 2,
    ShipmentStatus.LOADING: 2,
    ShipmentStatus.LOADED: 3,
    ShipmentStatus.OUT_FOR_DELIVERY: 3,
    ShipmentStatus.DELIVERED: 4,
    ShipmentStatus.DELIVERY_FAILED: 4,
    ShipmentStatus.CANCELED: 4,
    ShipmentStatus.UPDATED: 3,
}


def build_timeline_steps(status: str) -> list[dict]:
    rank = STATUS_RANKS.get(status, 0)
    steps = []

    for index, label in enumerate(TIMELINE_LABELS):
        if index < rank:
            state = "done"
        elif index == rank:
            state = "current"
        else:
            state = "todo"

        if status == ShipmentStatus.DELIVERED and index <= rank:
            state = "done"

        steps.append({"label": label, "state": state})

    return steps
