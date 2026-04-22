import logging

from django.db import transaction
from django.db.models import F

from store.models import Inventory, Product, Shipment, ShipmentItem, ShipmentStatus, Warehouse
from world_amazon_pb2 import ACommands, APurchaseMore

logger = logging.getLogger(__name__)
WORLD_DESCRIPTION_MAX_LEN = 50


def _world_description(value: str) -> str:
    return (value or "")[:WORLD_DESCRIPTION_MAX_LEN]


def process_created_shipments(world_client, ack_mgr, pending_buys: dict, world_id: int = None) -> None:
    """
    Poll for CREATED shipments. For each one:
      - If inventory is sufficient: reserve stock and advance to PACKING.
      - If not: issue APurchaseMore for the shortfall, stay in CREATED.

    pending_buys: shared dict  seqnum -> shipment_id  maintained by caller.
    Called periodically from the scheduler loop.
    """
    already_pending = set(pending_buys.values())
    shipments = Shipment.objects.filter(
        status=ShipmentStatus.CREATED
    )
    if world_id is not None:
        shipments = shipments.filter(world_id=world_id)
    shipments = shipments.prefetch_related("items__product", "warehouse")

    for shipment in shipments:
        if shipment.shipment_id in already_pending:
            continue
        _handle_created(shipment, world_client, ack_mgr, pending_buys)


def _handle_created(shipment, world_client, ack_mgr, pending_buys: dict) -> None:
    warehouse = shipment.warehouse
    items = list(shipment.items.select_related("product"))

    with transaction.atomic():
        # Re-read shipment with a row lock to prevent two threads from
        # processing the same shipment simultaneously.
        try:
            locked = Shipment.objects.select_for_update().get(
                pk=shipment.pk, status=ShipmentStatus.CREATED
            )
        except Shipment.DoesNotExist:
            return  # Another thread already advanced this shipment

        # Lock inventory rows for this warehouse to prevent race conditions.
        inv_map = {
            inv.product_id: inv
            for inv in Inventory.objects.select_for_update().filter(
                warehouse=warehouse,
                product__in=[item.product for item in items],
            )
        }

        shortfall = []
        for item in items:
            inv = inv_map.get(item.product_id)
            available = (inv.on_hand_count - inv.reserved_count) if inv else 0
            need = item.quantity - available
            if need > 0:
                shortfall.append((item.product, item.description_snapshot, need))

        if shortfall:
            _issue_buy(locked, warehouse, shortfall, world_client, ack_mgr, pending_buys)
            return

        # Enough stock: reserve it and move to PACKING.
        for item in items:
            inv = inv_map[item.product_id]
            inv.reserved_count += item.quantity
            inv.save(update_fields=["reserved_count", "updated_at"])

        locked.status = ShipmentStatus.PACKING
        locked.save(update_fields=["status", "updated_at"])
        logger.info("shipment %s advanced to PACKING (inventory sufficient)", locked.shipment_id)


def _issue_buy(shipment, warehouse, shortfall, world_client, ack_mgr, pending_buys: dict) -> None:
    seqnum = ack_mgr.next_seqnum()

    cmd = ACommands()
    buy = cmd.buy.add()
    buy.whnum = warehouse.warehouse_id
    buy.seqnum = seqnum
    for product, description, count in shortfall:
        thing = buy.things.add()
        thing.id = product.product_id
        thing.description = _world_description(description)
        thing.count = count

    world_client.send(cmd)
    ack_mgr.register(seqnum, cmd)
    pending_buys[seqnum] = shipment.shipment_id

    logger.info(
        "issued buy for shipment %s, seqnum=%d, shortfall=%s",
        shipment.shipment_id,
        seqnum,
        [(p.product_id, c) for p, _, c in shortfall],
    )


def handle_arrived(arrived: APurchaseMore, pending_buys: dict, world_id: int = None) -> list[str]:
    """
    Called when World confirms goods have arrived at a warehouse.
    Updates on_hand_count in Inventory and returns a list of shipment_ids
    that now have sufficient stock and should proceed to PACKING.

    NOTE: arrived.seqnum is the WORLD's own seqnum, not Amazon's command seqnum.
    We find the related shipment by matching warehouse + product contents.
    """
    arrived_product_ids = frozenset(thing.id for thing in arrived.things)
    shipment_id = None
    matched_seqnum = None
    for seq, sid in list(pending_buys.items()):
        try:
            s = Shipment.objects.get(shipment_id=sid)
            item_product_ids = frozenset(
                item.product.product_id for item in s.items.select_related("product")
            )
            if item_product_ids == arrived_product_ids:
                shipment_id = sid
                matched_seqnum = seq
                break
        except Shipment.DoesNotExist:
            pending_buys.pop(seq, None)

    if matched_seqnum is not None:
        pending_buys.pop(matched_seqnum, None)

    with transaction.atomic():
        qs = Warehouse.objects.filter(warehouse_id=arrived.whnum)
        if world_id:
            qs = qs.filter(world_id=world_id)
        warehouse = qs.first()
        if warehouse is None:
            logger.error("handle_arrived: warehouse %d not found", arrived.whnum)
            return []
        for thing in arrived.things:
            product, _ = Product.objects.get_or_create(
                product_id=thing.id,
                defaults={"description": thing.description},
            )
            inv, _ = Inventory.objects.get_or_create(
                warehouse=warehouse,
                product=product,
                defaults={"on_hand_count": 0, "reserved_count": 0},
            )
            Inventory.objects.filter(pk=inv.pk).update(
                on_hand_count=F("on_hand_count") + thing.count
            )
            logger.info(
                "arrived: warehouse=%d product=%d +%d",
                arrived.whnum, thing.id, thing.count,
            )

    ready = []
    if shipment_id:
        ready.append(shipment_id)
    return ready
