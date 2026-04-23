from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0006_alter_truck_truck_status"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="package",
            constraint=models.UniqueConstraint(
                fields=("world_id", "world_package_id"),
                condition=models.Q(world_package_id__isnull=False),
                name="uniq_pkg_world_worldpkg_notnull",
            ),
        ),
    ]
