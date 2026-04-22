from django.db import migrations, models


def seed_outbound_seq(apps, schema_editor):
    OutboundSeq = apps.get_model("interop", "OutboundSeq")
    OutboundSeq.objects.get_or_create(pk=1, defaults={"next_seq": 1})


class Migration(migrations.Migration):
    dependencies = [
        ("interop", "0002_remove_outboundcommand"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutboundSeq",
            fields=[
                ("id", models.PositiveSmallIntegerField(default=1, primary_key=True, serialize=False)),
                ("next_seq", models.BigIntegerField(default=1)),
            ],
            options={
                "db_table": "interop_outbound_seq",
            },
        ),
        migrations.RunPython(seed_outbound_seq, migrations.RunPython.noop),
    ]
