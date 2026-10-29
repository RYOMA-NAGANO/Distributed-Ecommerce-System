from django.conf import settings
from django.db import models


class Truck(models.Model):
    class TruckStatus(models.TextChoices):
        IDLE = "IDLE", "Idle"
        TRAVELING = "TRAVELING", "Traveling"
        ARRIVE_WAREHOUSE = "ARRIVE_WAREHOUSE", "Arrive Warehouse"
        LOADING = "LOADING", "Loading"
        DELIVERING = "DELIVERING", "Delivering"
        INVALID = "INVALID", "Invalid"

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
    shipment_id = models.CharField(max_length=100, primary_key=True)

    world_id = models.BigIntegerField(default=0, db_index=True)
    amazon_order_id = models.CharField(max_length=120, blank=True, default="")

    truck = models.ForeignKey(
        Truck,
        on_delete=models.SET_NULL,
        db_column="truck_id",
        null=True,
        blank=True,
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column="user_id",
    )

    dest_x = models.IntegerField()
    dest_y = models.IntegerField()

    warehouse_id = models.IntegerField(default=0)
    warehouse_x = models.IntegerField(default=0)
    warehouse_y = models.IntegerField(default=0)

    items = models.JSONField(null=True, blank=True)

    world_package_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    pickup_seqnum = models.BigIntegerField(null=True, blank=True, db_index=True)
    delivery_seqnum = models.BigIntegerField(null=True, blank=True, db_index=True)

    # AUIP / §2.7 lifecycle strings (created, truck_en_route, …)
    status = models.CharField(max_length=32, default="created", db_index=True)

    class Meta:
        db_table = "packages"
        constraints = [
            models.UniqueConstraint(
                fields=["world_id", "world_package_id"],
                condition=models.Q(world_package_id__isnull=False),
                name="uniq_pkg_world_worldpkg_notnull",
            )
        ]
        indexes = [
            # Hot path for the per-user package list (filter user + status).
            models.Index(fields=["user", "status"], name="pkg_user_status_idx"),
            # Hot path for daemon recovery/reconcile sweeps that filter by
            # world_id + status.
            models.Index(fields=["world_id", "status"], name="pkg_world_status_idx"),
        ]

    def __str__(self):
        return self.shipment_id


class PositionUpdate(models.Model):
    shipment = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        db_column="shipment_id",
        related_name="position_updates",
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
        related_name="destination_updates",
    )

    x = models.IntegerField()
    y = models.IntegerField()
    update_time = models.IntegerField()

    class Meta:
        db_table = "destination_updates"


class StatusUpdate(models.Model):
    shipment = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        db_column="shipment_id",
        related_name="status_updates",
    )

    status = models.CharField(max_length=32)
    update_time = models.IntegerField()

    class Meta:
        db_table = "status_updates"


class Warehouse(models.Model):
    warehouse_id = models.IntegerField(primary_key=True)
    x = models.IntegerField()
    y = models.IntegerField()

    class Meta:
        db_table = "warehouse"

    def __str__(self):
        return f"Warehouse {self.warehouse_id}"


class TrackedShipment(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tracked_shipments",
    )
    package = models.ForeignKey(
        Package,
        on_delete=models.CASCADE,
        related_name="tracked_by_users",
    )
    last_searched_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tracked_shipments"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "package"],
                name="unique_tracked_shipment_per_user",
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.package_id}"
