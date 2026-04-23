from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("interop", "0004_idempotencyrecord"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorldBinding",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False)),
                ("world_id", models.BigIntegerField()),
                ("result", models.CharField(blank=True, default="", max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "db_table": "interop_world_binding",
            },
        ),
    ]
