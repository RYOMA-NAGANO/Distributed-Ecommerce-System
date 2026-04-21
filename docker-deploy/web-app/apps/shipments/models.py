from django.conf import settings
from django.db import models


class Shipment(models.Model):
    STATUS_CREATED = "created"
    STATUS_PICKUP_PENDING = "pickup_pending"
    STATUS_PICKED_UP = "picked_up"
    STATUS_DELIVERING = "delivering"
    STATUS_DELIVERED = "delivered"

    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PICKUP_PENDING, "Waiting for pickup"),
        (STATUS_PICKED_UP, "Picked up"),
        (STATUS_DELIVERING, "Delivering"),
        (STATUS_DELIVERED, "Delivered"),
    ]

    tracking_number = models.CharField(max_length=64, unique=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipments",
    )
    status = models.CharField(max_length=32, choices=STATUS_CHOICES, default=STATUS_CREATED)
    destination_x = models.IntegerField()
    destination_y = models.IntegerField()
    amazon_reference = models.CharField(max_length=64, blank=True)
    truck_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.tracking_number
