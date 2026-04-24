from django.db import migrations


DEFAULT_TRUCK_IDS = (1, 2, 3)


def seed_default_trucks(apps, schema_editor):
    Truck = apps.get_model("core", "Truck")
    for truck_id in DEFAULT_TRUCK_IDS:
        Truck.objects.get_or_create(
            truck_id=truck_id,
            defaults={"truck_status": "IDLE"},
        )


def unseed_default_trucks(apps, schema_editor):
    Truck = apps.get_model("core", "Truck")
    Truck.objects.filter(
        truck_id__in=DEFAULT_TRUCK_IDS,
        package__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0008_statusupdate"),
    ]

    operations = [
        migrations.RunPython(seed_default_trucks, unseed_default_trucks),
    ]
