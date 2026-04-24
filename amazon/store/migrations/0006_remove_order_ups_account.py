from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0005_order_user"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="order",
            name="ups_account",
        ),
    ]
