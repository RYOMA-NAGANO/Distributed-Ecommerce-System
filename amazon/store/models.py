from django.db import models
from django.conf import settings


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ShipmentStatus(models.TextChoices):
    CREATED = "created", "Created"
    PACKING = "packing", "Packing"
    PACKED = "packed", "Packed"
    TRUCK_EN_ROUTE = "truck_en_route", "Truck En Route"
    TRUCK_ARRIVED = "truck_arrived", "Truck Arrived"
    LOADING = "loading", "Loading"
    LOADED = "loaded", "Loaded"
    OUT_FOR_DELIVERY = "out_for_delivery", "Out For Delivery"
    DELIVERED = "delivered", "Delivered"
    DELIVERY_FAILED = "delivery_failed", "Delivery Failed"
    CANCELED = "canceled", "Canceled"
    UPDATED = "updated", "Updated"


class HttpDirection(models.TextChoices):
    INBOUND = "inbound", "Inbound"
    OUTBOUND = "outbound", "Outbound"


class EventSource(models.TextChoices):
    WEB = "web", "Web"
    UPS = "ups", "UPS"
    WORLD = "world", "World"
    SYSTEM = "system", "System"


class Product(TimestampedModel):
    product_id = models.BigIntegerField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    description = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    category = models.CharField(max_length=64, blank=True)
    badge = models.CharField(max_length=64, blank=True)
    image_url = models.URLField(blank=True)

    class Meta:
        ordering = ["product_id"]

    def __str__(self):
        return f"{self.product_id}: {self.description}"


class Warehouse(TimestampedModel):
    world_id = models.BigIntegerField(db_index=True)
    warehouse_id = models.PositiveIntegerField(db_index=True)
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        ordering = ["world_id", "warehouse_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["world_id", "warehouse_id"],
                name="unique_warehouse_per_world",
            )
        ]

    def __str__(self):
        return f"World {self.world_id} / Warehouse {self.warehouse_id}"


class Inventory(TimestampedModel):
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.CASCADE,
        related_name="inventory_rows",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        related_name="inventory_rows",
    )
    on_hand_count = models.PositiveIntegerField(default=0)
    reserved_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["warehouse_id", "product_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["warehouse", "product"],
                name="unique_inventory_per_warehouse_product",
            )
        ]

    def __str__(self):
        return f"{self.warehouse} / {self.product.product_id}"


class Order(TimestampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders",
        null=True,
        blank=True,
    )
    amazon_order_id = models.CharField(max_length=64, unique=True, db_index=True)
    requested_destination_x = models.IntegerField()
    requested_destination_y = models.IntegerField()
    ups_account = models.CharField(max_length=128, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.amazon_order_id


class Shipment(TimestampedModel):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="shipments",
    )
    warehouse = models.ForeignKey(
        Warehouse,
        on_delete=models.PROTECT,
        related_name="shipments",
    )
    world_id = models.BigIntegerField(db_index=True)
    shipment_id = models.CharField(max_length=64, db_index=True)
    tracking_number = models.CharField(max_length=64, blank=True, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=ShipmentStatus.choices,
        default=ShipmentStatus.CREATED,
        db_index=True,
    )
    truck_id = models.PositiveIntegerField(null=True, blank=True, db_index=True)
    destination_x = models.IntegerField()
    destination_y = models.IntegerField()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["world_id", "shipment_id"],
                name="unique_shipment_per_world",
            )
        ]

    def __str__(self):
        return f"{self.shipment_id} ({self.status})"


class ShipmentItem(TimestampedModel):
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="shipment_items",
    )
    quantity = models.PositiveIntegerField()
    description_snapshot = models.CharField(max_length=255)

    class Meta:
        ordering = ["shipment_id", "product_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["shipment", "product"],
                name="unique_product_per_shipment",
            )
        ]

    def __str__(self):
        return f"{self.shipment.shipment_id} / {self.product.product_id}"


class HttpIdempotencyRecord(TimestampedModel):
    direction = models.CharField(max_length=16, choices=HttpDirection.choices)
    peer = models.CharField(max_length=32, blank=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    idempotency_key = models.CharField(max_length=128)
    body_hash = models.CharField(max_length=64)
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="idempotency_records",
    )
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["direction", "method", "path", "idempotency_key"],
                name="unique_http_idempotency_record",
            )
        ]

    def __str__(self):
        return f"{self.direction} {self.method} {self.path}"


class ShipmentEvent(TimestampedModel):
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    source = models.CharField(max_length=16, choices=EventSource.choices)
    event_type = models.CharField(max_length=64)
    world_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    status_snapshot = models.CharField(
        max_length=32,
        choices=ShipmentStatus.choices,
        blank=True,
    )
    payload = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        if self.shipment:
            return f"{self.source}:{self.event_type} for {self.shipment.shipment_id}"
        return f"{self.source}:{self.event_type}"
