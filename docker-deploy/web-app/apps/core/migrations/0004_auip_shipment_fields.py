from django.conf import settings
from django.db import migrations, models


def forwards_status(apps, schema_editor):
    Package = apps.get_model("core", "Package")
    mapping = {
        "CREATED": "created",
        "LOADING": "loading",
        "DELIVERING": "out_for_delivery",
        "DELIVERED": "delivered",
    }
    for row in Package.objects.all():
        new_s = mapping.get(row.status, row.status or "created")
        row.status = new_s
        row.save(update_fields=["status"])


def create_interop_user(apps, schema_editor):
    User = apps.get_model("auth", "User")
    if User.objects.filter(username="_amazon_interop").exists():
        return
    # In migrations, historical model classes do not expose helper methods
    # such as set_unusable_password(), so we set an unusable marker directly.
    user = User(username="_amazon_interop", email="interop@miniups.local", password="!")
    user.save()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_alter_package_warehouse_id"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="package",
            name="world_id",
            field=models.BigIntegerField(db_index=True, default=0),
        ),
        migrations.AddField(
            model_name="package",
            name="amazon_order_id",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="package",
            name="warehouse_x",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="package",
            name="warehouse_y",
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name="package",
            name="items",
            field=models.JSONField(blank=True, null=True),
        ),
        migrations.RunPython(create_interop_user, migrations.RunPython.noop),
        migrations.RunPython(forwards_status, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="package",
            name="status",
            field=models.CharField(default="created", max_length=32),
        ),
    ]
