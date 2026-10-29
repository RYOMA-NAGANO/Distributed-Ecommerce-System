from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0009_seed_default_trucks"),
    ]

    operations = [
        migrations.AlterField(
            model_name="package",
            name="status",
            field=models.CharField(db_index=True, default="created", max_length=32),
        ),
        migrations.AddIndex(
            model_name="package",
            index=models.Index(fields=["user", "status"], name="pkg_user_status_idx"),
        ),
        migrations.AddIndex(
            model_name="package",
            index=models.Index(fields=["world_id", "status"], name="pkg_world_status_idx"),
        ),
    ]
