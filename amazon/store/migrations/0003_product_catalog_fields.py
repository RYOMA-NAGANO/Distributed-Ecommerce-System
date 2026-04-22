from decimal import Decimal

from django.db import migrations, models


CATALOG_SEED_PRODUCTS = [
    {
        "product_id": 1001,
        "name": "Compact Shipping Box Set",
        "description": "Basic corrugated shipping boxes for project demos and early testing.",
        "price": Decimal("24.99"),
        "badge": "Amazon Lite Choice",
        "category": "Packaging",
    },
    {
        "product_id": 1002,
        "name": "Campus Laptop Stand",
        "description": "Simple aluminum stand for a clean desk setup and product card previews.",
        "price": Decimal("39.50"),
        "badge": "Popular",
        "category": "Office",
    },
    {
        "product_id": 1003,
        "name": "Starter Cable Organizer",
        "description": "Lightweight organizer used as placeholder inventory for the first sprint.",
        "price": Decimal("12.00"),
        "badge": "New Arrival",
        "category": "Accessories",
    },
    {
        "product_id": 1004,
        "name": "Desk Lamp Mini",
        "description": "Compact desk lamp for simple workspace setups and demo catalog coverage.",
        "price": Decimal("18.90"),
        "badge": "Top Rated",
        "category": "Office",
    },
    {
        "product_id": 1005,
        "name": "USB-C Hub Basic",
        "description": "Small multi-port hub used as another lightweight storefront sample item.",
        "price": Decimal("27.50"),
        "badge": "Popular",
        "category": "Accessories",
    },
    {
        "product_id": 1006,
        "name": "Mailer Envelope Pack",
        "description": "Padded mailers for shipment demos, packing tests, and order detail previews.",
        "price": Decimal("16.25"),
        "badge": "Project Pick",
        "category": "Packaging",
    },
    {
        "product_id": 1007,
        "name": "Wireless Mouse",
        "description": "Simple wireless mouse used to make the product list feel more complete.",
        "price": Decimal("21.99"),
        "badge": "In Stock",
        "category": "Accessories",
    },
    {
        "product_id": 1008,
        "name": "Notebook Pack",
        "description": "Classic notebook set for office and student-facing sample product coverage.",
        "price": Decimal("14.75"),
        "badge": "Budget Pick",
        "category": "Office",
    },
    {
        "product_id": 1009,
        "name": "Bubble Wrap Roll",
        "description": "Protective packaging material for shipment-related demos and mock inventory.",
        "price": Decimal("29.80"),
        "badge": "Warehouse Favorite",
        "category": "Packaging",
    },
    {
        "product_id": 1010,
        "name": "Keyboard Wrist Rest",
        "description": "Small ergonomic desk accessory that rounds out the first sample catalog.",
        "price": Decimal("19.40"),
        "badge": "Popular",
        "category": "Office",
    },
    {
        "product_id": 1011,
        "name": "Portable SSD Sleeve",
        "description": "Protective accessory item for a cleaner mid-price section in the catalog.",
        "price": Decimal("13.60"),
        "badge": "New Arrival",
        "category": "Accessories",
    },
    {
        "product_id": 1012,
        "name": "Packing Tape Bundle",
        "description": "Basic tape bundle to support the packing and warehouse side of the demo.",
        "price": Decimal("11.95"),
        "badge": "Amazon Lite Choice",
        "category": "Packaging",
    },
]


def populate_catalog_fields(apps, schema_editor):
    Product = apps.get_model("store", "Product")

    for product in CATALOG_SEED_PRODUCTS:
        Product.objects.filter(product_id=product["product_id"]).update(
            name=product["name"],
            description=product["description"],
            price=product["price"],
            category=product["category"],
            badge=product["badge"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0002_seed_catalog_products"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddField(
            model_name="product",
            name="price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="product",
            name="category",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="product",
            name="badge",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="product",
            name="image_url",
            field=models.URLField(blank=True),
        ),
        migrations.RunPython(populate_catalog_fields, migrations.RunPython.noop),
    ]
