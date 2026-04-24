from django.contrib import admin

from .models import (
    HttpIdempotencyRecord,
    Inventory,
    Order,
    Product,
    Shipment,
    ShipmentEvent,
    ShipmentItem,
    Warehouse,
)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("product_id", "name", "price", "category", "updated_at")
    search_fields = ("product_id", "name", "description", "category")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("warehouse_id", "world_id", "x", "y", "updated_at")
    list_filter = ("world_id",)
    search_fields = ("warehouse_id", "world_id")


@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = (
        "warehouse",
        "product",
        "on_hand_count",
        "reserved_count",
        "updated_at",
    )
    list_filter = ("warehouse",)
    search_fields = ("warehouse__warehouse_id", "product__product_id")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "amazon_order_id",
        "user",
        "requested_destination_x",
        "requested_destination_y",
        "created_at",
    )
    list_filter = ("user",)
    search_fields = ("amazon_order_id", "user__username", "user__email")


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = (
        "shipment_id",
        "world_id",
        "status",
        "truck_id",
        "tracking_number",
        "order",
        "warehouse",
        "updated_at",
    )
    list_filter = ("status", "world_id")
    search_fields = (
        "shipment_id",
        "tracking_number",
        "order__amazon_order_id",
        "order__user__username",
        "order__user__email",
    )


@admin.register(ShipmentItem)
class ShipmentItemAdmin(admin.ModelAdmin):
    list_display = ("shipment", "product", "quantity", "description_snapshot")
    search_fields = ("shipment__shipment_id", "product__product_id")


@admin.register(HttpIdempotencyRecord)
class HttpIdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = (
        "direction",
        "peer",
        "method",
        "path",
        "idempotency_key",
        "response_status",
        "created_at",
    )
    list_filter = ("direction", "peer", "method")
    search_fields = ("idempotency_key", "path", "shipment__shipment_id")


@admin.register(ShipmentEvent)
class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "event_type",
        "shipment",
        "world_id",
        "status_snapshot",
        "created_at",
    )
    list_filter = ("source", "status_snapshot", "world_id")
    search_fields = ("event_type", "shipment__shipment_id")
