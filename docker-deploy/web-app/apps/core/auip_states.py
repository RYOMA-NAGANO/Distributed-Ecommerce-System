"""AUIP shipment status strings (interfaces.MD §2.7)."""

CREATED = "created"
PACKING = "packing"
PACKED = "packed"
TRUCK_EN_ROUTE = "truck_en_route"
TRUCK_ARRIVED = "truck_arrived"
LOADING = "loading"
LOADED = "loaded"
OUT_FOR_DELIVERY = "out_for_delivery"
DELIVERED = "delivered"
DELIVERY_FAILED = "delivery_failed"
CANCELED = "canceled"
UPDATED = "updated"

PICKUP_BLOCKED = frozenset({LOADED, OUT_FOR_DELIVERY, DELIVERED, CANCELED})

READY_BLOCKED = frozenset({LOADED, OUT_FOR_DELIVERY, DELIVERED, CANCELED})

DESTINATION_BLOCKED = frozenset({OUT_FOR_DELIVERY, DELIVERED, CANCELED})
