from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("interop", "0003_outboundseq"),
    ]

    operations = [
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("key", models.CharField(max_length=64)),
                ("method", models.CharField(max_length=8)),
                ("path", models.CharField(max_length=512)),
                ("body_hash", models.CharField(max_length=64)),
                ("response_status", models.PositiveSmallIntegerField()),
                ("response_body", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "interop_idempotency",
            },
        ),
        migrations.AddConstraint(
            model_name="idempotencyrecord",
            constraint=models.UniqueConstraint(fields=("key", "method", "path"), name="interop_idem_key_method_path"),
        ),
    ]
