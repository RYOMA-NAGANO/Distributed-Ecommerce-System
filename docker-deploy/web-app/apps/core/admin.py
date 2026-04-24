from django.contrib import admin

from .models import (
    DestinationUpdate,
    Package,
    PositionUpdate,
    StatusUpdate,
    TrackedShipment,
    Truck,
    Warehouse,
)


@admin.register(Truck)
class TruckAdmin(admin.ModelAdmin):
    list_display = ("truck_id", "truck_status")
    list_filter = ("truck_status",)


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = (
        "shipment_id",
        "status",
        "user",
        "truck",
        "warehouse_id",
        "world_package_id",
        "pickup_seqnum",
        "delivery_seqnum",
        "dest_x",
        "dest_y",
    )
    list_filter = ("status",)
    search_fields = ("shipment_id", "user__username")
    raw_id_fields = ("user", "truck")


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ("warehouse_id", "x", "y")


@admin.register(PositionUpdate)
class PositionUpdateAdmin(admin.ModelAdmin):
    list_display = ("id", "shipment", "x", "y", "update_time")
    list_filter = ("shipment",)


@admin.register(DestinationUpdate)
class DestinationUpdateAdmin(admin.ModelAdmin):
    list_display = ("id", "shipment", "x", "y", "update_time")


@admin.register(StatusUpdate)
class StatusUpdateAdmin(admin.ModelAdmin):
    list_display = ("id", "shipment", "status", "update_time")
    list_filter = ("status",)


@admin.register(TrackedShipment)
class TrackedShipmentAdmin(admin.ModelAdmin):
    list_display = ("user", "package", "last_searched_at")
    search_fields = ("user__username", "package__shipment_id", "package__amazon_order_id")
