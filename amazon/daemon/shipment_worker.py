import logging

from django.db import transaction
from django.db.models import F

from store.models import Inventory, Shipment, ShipmentStatus
from world_amazon_pb2 import ACommands

logger = logging.getLogger(__name__)
WORLD_DESCRIPTION_MAX_LEN = 50


def _world_description(value: str) -> str:
    return (value or "")[:WORLD_DESCRIPTION_MAX_LEN]


def issue_topack(shipment, world_client, ack_mgr, pending_packs: dict) -> None:
    """
    Send APack to the world simulator for a PACKING shipment.
    pending_packs: seqnum -> shipment_id
    """
    seqnum = ack_mgr.next_seqnum()

    cmd = ACommands()
    pack = cmd.topack.add()
    pack.whnum = shipment.warehouse.warehouse_id
    pack.shipid = int(shipment.shipment_id)
    pack.seqnum = seqnum
    for item in shipment.items.select_related("product"):
        thing = pack.things.add()
        thing.id = item.product.product_id
        thing.description = _world_description(item.description_snapshot)
        thing.count = item.quantity

    world_client.send(cmd)
    ack_mgr.register(seqnum, cmd)
    pending_packs[seqnum] = shipment.shipment_id

    logger.info("issued topack for shipment %s seqnum=%d", shipment.shipment_id, seqnum)


def handle_ready(packed_msg, pending_packs: dict) -> str | None:
    """
    Called when World confirms packing is done (APacked response).
    Updates shipment status to PACKED.
    Returns shipment_id if it should now wait for truck or load immediately.
    """
    shipment_id = str(packed_msg.shipid)
    pending_packs.pop(packed_msg.seqnum, None)

    try:
        with transaction.atomic():
            shipment = Shipment.objects.select_for_update().get(shipment_id=shipment_id)
            if shipment.status == ShipmentStatus.PACKING:
                shipment.status = ShipmentStatus.PACKED
                shipment.save(update_fields=["status", "updated_at"])
                updated = True
            elif shipment.status == ShipmentStatus.TRUCK_ARRIVED:
                updated = True
            else:
                updated = False
    except Shipment.DoesNotExist:
        logger.error("handle_ready: shipment %s not found", shipment_id)
        return None

    if updated:
        logger.info("shipment %s is PACKED", shipment_id)
        return shipment_id
    return None


def try_issue_load(shipment_id: str, world_client, ack_mgr, pending_loads: dict) -> bool:
    """
    Load a shipment onto its truck if both conditions are met:
      - status is PACKED or TRUCK_ARRIVED
      - truck_id is set (UPS sent truck-arrived callback)

    Returns True if load command was issued.
    pending_loads: seqnum -> shipment_id
    """
    try:
        shipment = Shipment.objects.select_related("warehouse").get(shipment_id=shipment_id)
    except Shipment.DoesNotExist:
        return False

    both_ready = (
        shipment.status in (ShipmentStatus.PACKED, ShipmentStatus.TRUCK_ARRIVED)
        and shipment.truck_id is not None
    )
    if not both_ready:
        return False

    with transaction.atomic():
        locked = Shipment.objects.select_for_update().select_related("warehouse").get(
            shipment_id=shipment_id
        )
        if locked.status not in (ShipmentStatus.PACKED, ShipmentStatus.TRUCK_ARRIVED):
            return False
        if locked.truck_id is None:
            return False
        warehouse_id = locked.warehouse.warehouse_id
        truck_id = locked.truck_id
        locked.status = ShipmentStatus.LOADING
        locked.save(update_fields=["status", "updated_at"])

    seqnum = ack_mgr.next_seqnum()
    cmd = ACommands()
    load = cmd.load.add()
    load.whnum = warehouse_id
    load.truckid = truck_id
    load.shipid = int(shipment_id)
    load.seqnum = seqnum

    world_client.send(cmd)
    ack_mgr.register(seqnum, cmd)
    pending_loads[seqnum] = shipment_id

    logger.info(
        "issued load for shipment %s truck=%d seqnum=%d",
        shipment_id, truck_id, seqnum,
    )
    return True


def handle_loaded(loaded_msg, pending_loads: dict) -> str | None:
    """
    Called when World confirms the package is on the truck (ALoaded response).
    Updates status to LOADED and releases reserved inventory.
    Returns shipment_id for the caller to notify UPS.
    """
    shipment_id = str(loaded_msg.shipid)
    pending_loads.pop(loaded_msg.seqnum, None)

    with transaction.atomic():
        try:
            shipment = (
                Shipment.objects.select_for_update()
                .select_related("warehouse")
                .prefetch_related("items__product")
                .get(shipment_id=shipment_id)
            )
        except Shipment.DoesNotExist:
            logger.error("handle_loaded: shipment %s not found", shipment_id)
            return None

        if shipment.status == ShipmentStatus.LOADED:
            logger.info("handle_loaded: shipment %s already LOADED", shipment_id)
            return None
        if shipment.status != ShipmentStatus.LOADING:
            logger.warning(
                "handle_loaded: shipment %s in unexpected status %s",
                shipment_id,
                shipment.status,
            )
            return None

        shipment.status = ShipmentStatus.LOADED
        shipment.save(update_fields=["status", "updated_at"])

        # Release reserved inventory now that goods have left the warehouse.
        for item in shipment.items.all():
            Inventory.objects.filter(
                warehouse=shipment.warehouse,
                product=item.product,
            ).update(
                on_hand_count=F("on_hand_count") - item.quantity,
                reserved_count=F("reserved_count") - item.quantity,
            )

    logger.info("shipment %s is LOADED, inventory released", shipment_id)
    return shipment_id
