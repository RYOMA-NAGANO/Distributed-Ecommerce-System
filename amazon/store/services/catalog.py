from decimal import Decimal, ROUND_HALF_UP

from store.models import Product


_BASE_CATALOG_PRODUCTS = [
    {
        "product_id": "1001",
        "name": "Compact Shipping Box Set",
        "description": "Basic corrugated shipping boxes for project demos and early testing.",
        "price": "24.99",
        "badge": "Amazon Lite Choice",
        "category": "Packaging",
    },
    {
        "product_id": "1002",
        "name": "Campus Laptop Stand",
        "description": "Simple aluminum stand for a clean desk setup and product card previews.",
        "price": "39.50",
        "badge": "Popular",
        "category": "Office",
    },
    {
        "product_id": "1003",
        "name": "Starter Cable Organizer",
        "description": "Lightweight organizer used as placeholder inventory for the first sprint.",
        "price": "12.00",
        "badge": "New Arrival",
        "category": "Accessories",
    },
    {
        "product_id": "1004",
        "name": "Desk Lamp Mini",
        "description": "Compact desk lamp for simple workspace setups and demo catalog coverage.",
        "price": "18.90",
        "badge": "Top Rated",
        "category": "Office",
    },
    {
        "product_id": "1005",
        "name": "USB-C Hub Basic",
        "description": "Small multi-port hub used as another lightweight storefront sample item.",
        "price": "27.50",
        "badge": "Popular",
        "category": "Accessories",
    },
    {
        "product_id": "1006",
        "name": "Mailer Envelope Pack",
        "description": "Padded mailers for shipment demos, packing tests, and order detail previews.",
        "price": "16.25",
        "badge": "Project Pick",
        "category": "Packaging",
    },
    {
        "product_id": "1007",
        "name": "Wireless Mouse",
        "description": "Simple wireless mouse used to make the product list feel more complete.",
        "price": "21.99",
        "badge": "In Stock",
        "category": "Accessories",
    },
    {
        "product_id": "1008",
        "name": "Notebook Pack",
        "description": "Classic notebook set for office and student-facing sample product coverage.",
        "price": "14.75",
        "badge": "Budget Pick",
        "category": "Office",
    },
    {
        "product_id": "1009",
        "name": "Bubble Wrap Roll",
        "description": "Protective packaging material for shipment-related demos and mock inventory.",
        "price": "29.80",
        "badge": "Warehouse Favorite",
        "category": "Packaging",
    },
    {
        "product_id": "1010",
        "name": "Keyboard Wrist Rest",
        "description": "Small ergonomic desk accessory that rounds out the first sample catalog.",
        "price": "19.40",
        "badge": "Popular",
        "category": "Office",
    },
    {
        "product_id": "1011",
        "name": "Portable SSD Sleeve",
        "description": "Protective accessory item for a cleaner mid-price section in the catalog.",
        "price": "13.60",
        "badge": "New Arrival",
        "category": "Accessories",
    },
    {
        "product_id": "1012",
        "name": "Packing Tape Bundle",
        "description": "Basic tape bundle to support the packing and warehouse side of the demo.",
        "price": "11.95",
        "badge": "Amazon Lite Choice",
        "category": "Packaging",
    },
]

_GENERATED_CATALOG_FAMILIES = [
    {
        "category": "Packaging",
        "prefix": "Transit",
        "badge_cycle": [
            "Warehouse Favorite",
            "Project Pick",
            "Amazon Lite Choice",
            "Bulk Ready",
        ],
        "price_start": "8.40",
        "price_step": "1.15",
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
        "price_start": "11.90",
        "price_step": "1.35",
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
        "price_start": "13.25",
        "price_step": "1.55",
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
        "price_start": "15.10",
        "price_step": "1.45",
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


def _price_string(base_price: str, step: str, offset: int, family_index: int) -> str:
    value = (
        Decimal(base_price)
        + (Decimal(step) * offset)
        + (Decimal("0.45") * family_index)
    ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{value:.2f}"


def _build_generated_catalog_products() -> list[dict]:
    generated = []
    next_product_id = 1013

    for family_index, family in enumerate(_GENERATED_CATALOG_FAMILIES):
        templates = family["templates"]
        badge_cycle = family["badge_cycle"]
        for item_index, item_name in enumerate(family["items"]):
            full_name = f'{family["prefix"]} {item_name}'
            generated.append(
                {
                    "product_id": str(next_product_id),
                    "name": full_name,
                    "description": templates[item_index % len(templates)].format(name=full_name),
                    "price": _price_string(
                        family["price_start"],
                        family["price_step"],
                        item_index,
                        family_index,
                    ),
                    "badge": badge_cycle[item_index % len(badge_cycle)],
                    "category": family["category"],
                }
            )
            next_product_id += 1

    return generated


CATALOG_SEED_PRODUCTS = _BASE_CATALOG_PRODUCTS + _build_generated_catalog_products()

CATALOG_METADATA_BY_ID = {
    product["product_id"]: product for product in CATALOG_SEED_PRODUCTS
}


def get_catalog_products() -> list[dict]:
    db_products = {
        str(product.product_id): _build_product_view(product)
        for product in Product.objects.all().order_by("product_id")
    }

    merged_products = []
    seen_product_ids = set()

    for seed_product in CATALOG_SEED_PRODUCTS:
        product_id = seed_product["product_id"]
        merged_products.append(db_products.get(product_id, seed_product.copy()))
        seen_product_ids.add(product_id)

    for product_id in sorted(db_products.keys(), key=int):
        if product_id not in seen_product_ids:
            merged_products.append(db_products[product_id])

    return merged_products


def get_catalog_product(product_id: str) -> dict | None:
    try:
        numeric_product_id = int(product_id)
    except (TypeError, ValueError):
        return None

    product = Product.objects.filter(product_id=numeric_product_id).first()
    if product:
        return _build_product_view(product)
    return CATALOG_METADATA_BY_ID.get(str(product_id))


def get_catalog_metadata(product_id) -> dict:
    return CATALOG_METADATA_BY_ID.get(str(product_id), {})


def _build_product_view(product: Product) -> dict:
    metadata = get_catalog_metadata(product.product_id)
    return {
        "product_id": str(product.product_id),
        "name": product.name or metadata.get("name", product.description),
        "description": product.description,
        "price": str(product.price or metadata.get("price", "0.00")),
        "badge": product.badge or metadata.get("badge", "Catalog Item"),
        "category": product.category or metadata.get("category", "General"),
        "image_url": product.image_url,
    }
