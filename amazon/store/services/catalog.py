from store.models import Product


CATALOG_SEED_PRODUCTS = [
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

CATALOG_METADATA_BY_ID = {
    product["product_id"]: product for product in CATALOG_SEED_PRODUCTS
}


def get_catalog_products() -> list[dict]:
    products = list(Product.objects.all().order_by("product_id"))
    if not products:
        return CATALOG_SEED_PRODUCTS.copy()

    return [_build_product_view(product) for product in products]


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
