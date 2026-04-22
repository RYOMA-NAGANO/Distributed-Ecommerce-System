from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_auip_shipment_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TrackedShipment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_searched_at", models.DateTimeField(auto_now=True)),
                (
                    "package",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="tracked_by_users",
                        to="core.package",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="tracked_shipments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "tracked_shipments",
            },
        ),
        migrations.AddConstraint(
            model_name="trackedshipment",
            constraint=models.UniqueConstraint(
                fields=("user", "package"),
                name="unique_tracked_shipment_per_user",
            ),
        ),
    ]
