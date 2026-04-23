from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("interop", "0005_worldbinding"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorldResponseSeq",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("world_id", models.BigIntegerField()),
                ("seqnum", models.BigIntegerField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "interop_world_response_seq",
            },
        ),
        migrations.AddConstraint(
            model_name="worldresponseseq",
            constraint=models.UniqueConstraint(
                fields=("world_id", "seqnum"),
                name="uniq_world_response_seq",
            ),
        ),
    ]
