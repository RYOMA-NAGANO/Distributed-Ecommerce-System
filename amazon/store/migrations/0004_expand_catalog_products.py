from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations


BASE_CATALOG_PRODUCTS = [
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

GENERATED_CATALOG_FAMILIES = [
    {
        "category": "Packaging",
        "prefix": "Transit",
        "badge_cycle": [
            "Warehouse Favorite",
            "Project Pick",
            "Amazon Lite Choice",
            "Bulk Ready",
        ],
        "price_start": Decimal("8.40"),
        "price_step": Decimal("1.15"),
        "templates": [
            "{name} keeps warehouse packing demos stocked and ready for shipment prep.",
            "{name} adds practical variety for packing stations, inventory rows, and order previews.",
            "{name} is a simple packaging staple for labels, cartons, and shipping workflows.",
        ],
        "items": [
            "Label Roll",
            "Mailer Pouch",
            "Foam Sheet Kit",
            "Carton Cutter",
            "Packing Paper Set",
            "Corner Guard Pack",
            "Shipping Tube Bundle",
            "Return Sticker Kit",
            "Cushion Sleeve Set",
            "Poly Bag Stack",
            "Tape Gun",
            "Box Divider Pack",
            "Inventory Tag Kit",
            "Zip Tie Bundle",
            "Seal Strip Set",
            "Pallet Wrap Mini",
            "Cushion Pad Set",
            "Label Holder Pack",
            "Fragile Stamp Kit",
            "Carton Seal Tabs",
            "Address Sleeve Pack",
            "Packing Insert Cards",
        ],
    },
    {
        "category": "Office",
        "prefix": "Desk",
        "badge_cycle": [
            "Top Rated",
            "Popular",
            "Workspace Pick",
            "Budget Pick",
        ],
        "price_start": Decimal("11.90"),
        "price_step": Decimal("1.35"),
        "templates": [
            "{name} rounds out the office aisle with an easy desk setup accessory.",
            "{name} helps the storefront feel fuller with a practical workspace item.",
            "{name} is a straightforward office essential for demos, browsing, and checkout flows.",
        ],
        "items": [
            "Monitor Riser",
            "Desk Organizer",
            "Pen Cup Set",
            "Paper Tray",
            "Task Light",
            "Note Card Box",
            "File Folder Kit",
            "Calendar Stand",
            "Whiteboard Mini",
            "Keyboard Cover",
            "Mouse Pad Pro",
            "Binder Clip Jar",
            "Stapler Compact",
            "Cable Tray",
            "Document Sleeve Pack",
            "Desk Shelf",
            "Planner Notebook",
            "Phone Stand",
            "Webcam Cover Set",
            "Meeting Timer",
            "Pencil Case",
            "Receipt Holder",
        ],
    },
    {
        "category": "Accessories",
        "prefix": "Connect",
        "badge_cycle": [
            "New Arrival",
            "Popular",
            "In Stock",
            "Campus Pick",
        ],
        "price_start": Decimal("13.25"),
        "price_step": Decimal("1.55"),
        "templates": [
            "{name} gives the catalog another portable tech accessory for student-friendly browsing.",
            "{name} adds lightweight electronics coverage without changing the existing demo flow.",
            "{name} is an easy accessory item for carts, orders, and shipment practice.",
        ],
        "items": [
            "USB-C Cable",
            "HDMI Adapter",
            "Bluetooth Keypad",
            "Charger Stand",
            "Earbud Case",
            "Laptop Sleeve",
            "Power Bank Mini",
            "Webcam Mount",
            "SD Card Wallet",
            "Desk Fan USB",
            "Screen Cloth Kit",
            "Dongle Pouch",
            "Travel Adapter",
            "Charging Brick",
            "Cable Clip Set",
            "Keyboard Brush",
            "Tablet Stand",
            "Microphone Arm Mini",
            "Stylus Pen",
            "Hub Organizer",
            "Phone Grip",
            "Trackpad Sleeve",
        ],
    },
    {
        "category": "Storage",
        "prefix": "Store",
        "badge_cycle": [
            "Space Saver",
            "Project Pick",
            "Warehouse Favorite",
            "New Arrival",
        ],
        "price_start": Decimal("15.10"),
        "price_step": Decimal("1.45"),
        "templates": [
            "{name} expands the storage section with a clean, practical organization item.",
            "{name} supports warehouse and home organization demos with a simple utility product.",
            "{name} helps the catalog reach deeper variety for sorting, shelving, and storage flows.",
        ],
        "items": [
            "Shelf Bin",
            "Drawer Insert",
            "Crate Label Set",
            "Stackable Box",
            "File Tote",
            "Closet Hook Pack",
            "Underdesk Basket",
            "Cable Bin",
            "Supply Caddy",
            "Foldable Crate",
            "Door Rack Mini",
            "Tool Tray",
            "Archive Box",
            "Storage Cube",
            "Organizer Lid Set",
            "Pantry Bin",
            "Basket Liner Pack",
            "Utility Hook Set",
            "Rolling Cart Bin",
            "Parts Drawer Kit",
            "Label Pocket Pack",
            "Sorting Tray",
        ],
    },
]


def _build_catalog_products():
    products = list(BASE_CATALOG_PRODUCTS)
    next_product_id = 1013

    for family_index, family in enumerate(GENERATED_CATALOG_FAMILIES):
        for item_index, item_name in enumerate(family["items"]):
            name = f'{family["prefix"]} {item_name}'
            price = (
                family["price_start"]
                + (family["price_step"] * item_index)
                + (Decimal("0.45") * family_index)
            ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            products.append(
                {
                    "product_id": next_product_id,
                    "name": name,
                    "description": family["templates"][item_index % len(family["templates"])].format(
                        name=name
                    ),
                    "price": price,
                    "badge": family["badge_cycle"][item_index % len(family["badge_cycle"])],
                    "category": family["category"],
                }
            )
            next_product_id += 1

    return products


def seed_expanded_catalog(apps, schema_editor):
    Product = apps.get_model("store", "Product")

    for product in _build_catalog_products():
        Product.objects.update_or_create(
            product_id=product["product_id"],
            defaults={
                "name": product["name"],
                "description": product["description"],
                "price": product["price"],
                "category": product["category"],
                "badge": product["badge"],
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("store", "0003_product_catalog_fields"),
    ]

    operations = [
        migrations.RunPython(seed_expanded_catalog, migrations.RunPython.noop),
    ]
