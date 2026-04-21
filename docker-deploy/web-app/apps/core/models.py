from django.db import models
from django.core.exceptions import ValidationError

from ..accounts.models import User

class Truck(models.Model):
    class TruckStatus(models.TextChoices):
        IDLE = "IDLE", "Idle"
        TRAVELING = "TRAVELING", "Traveling"
        LOADING = "LOADING", "Loading"
        DELIVERING = "DELIVERING", "Delivering"

    truck_id = models.IntegerField(primary_key=True)
    truck_status = models.CharField(
        max_length=20,
        choices=TruckStatus.choices,
        default=TruckStatus.IDLE,
    )

    class Meta:
        db_table = "trucks"

    def __str__(self):
        return f"Truck {self.truck_id} ({self.truck_status})"


class Package(models.Model):
    class Status(models.TextChoices):
        CREATED = "CREATED"
        LOADING = "LOADING"
        DELIVERING = "DELIVERING"
        DELIVERED = "DELIVERED"

    shipment_id = models.CharField(
        max_length=100,
        primary_key=True
    )

    truck = models.ForeignKey(
        Truck,
        on_delete=models.SET_NULL,
        db_column="truck_id",
        null=True,
        blank=True
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id"
    )

    dest_x = models.IntegerField()
    dest_y = models.IntegerField()

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED
    )

    class Meta:
        db_table = "packages"

    def __str__(self):
        return self.shipment_id

class PositionUpdate(models.Model):
    shipment = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        db_column="shipment_id",
        related_name="position_updates"
    )

    x = models.IntegerField()
    y = models.IntegerField()
    update_time = models.IntegerField()

    class Meta:
        db_table = "position_updates"

class DestinationUpdate(models.Model):
    shipment = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        db_column="shipment_id",
        related_name="destination_updates"
    )

    x = models.IntegerField()
    y = models.IntegerField()
    update_time = models.IntegerField()

    class Meta:
        db_table = "destination_updates"

class Warehouse(models.Model):
    warehouse_id = models.IntegerField(primary_key=True)
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        db_table = "warehouse"

    def __str__(self):
        return f"Warehouse {self.warehouse_id}"