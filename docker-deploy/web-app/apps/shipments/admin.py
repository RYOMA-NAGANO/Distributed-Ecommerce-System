from django.contrib import admin

from .models import Shipment


@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = ("tracking_number", "status", "truck_id", "created_at")
    search_fields = ("tracking_number", "amazon_reference")
    list_filter = ("status",)
