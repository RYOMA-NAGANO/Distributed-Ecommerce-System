from django.db import migrations


CATALOG_SEED_PRODUCTS = [
    (1001, "Basic corrugated shipping boxes for project demos and early testing."),
    (1002, "Simple aluminum stand for a clean desk setup and product card previews."),
    (1003, "Lightweight organizer used as placeholder inventory for the first sprint."),
    (1004, "Compact desk lamp for simple workspace setups and demo catalog coverage."),
    (1005, "Small multi-port hub used as another lightweight storefront sample item."),
    (1006, "Padded mailers for shipment demos, packing tests, and order detail previews."),
    (1007, "Simple wireless mouse used to make the product list feel more complete."),
    (1008, "Classic notebook set for office and student-facing sample product coverage."),
    (1009, "Protective packaging material for shipment-related demos and mock inventory."),
    (1010, "Small ergonomic desk accessory that rounds out the first sample catalog."),
    (1011, "Protective accessory item for a cleaner mid-price section in the catalog."),
    (1012, "Basic tape bundle to support the packing and warehouse side of the demo."),
]


def seed_catalog_products(apps, schema_editor):
    Product = apps.get_model("store", "Product")

    for product_id, description in CATALOG_SEED_PRODUCTS:
        Product.objects.get_or_create(
            product_id=product_id,
            defaults={"description": description},
        )


def unseed_catalog_products(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    Product.objects.filter(
        product_id__in=[product_id for product_id, _description in CATALOG_SEED_PRODUCTS]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_catalog_products, unseed_catalog_products),
    ]
