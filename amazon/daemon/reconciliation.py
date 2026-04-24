import logging

from store.models import Shipment, ShipmentStatus
import shipment_worker

logger = logging.getLogger(__name__)


def reconcile(world_client, ack_mgr, pending_packs: dict, pending_loads: dict, world_id: int = None) -> None:
    """
    Called once after daemon (re)connects to the world simulator.

    Scans the DB for shipments stuck in an in-progress state and re-issues
    the appropriate world commands so the pipeline can continue.

    CREATED shipments are intentionally skipped — the scheduler's poll loop
    handles them on its first tick.
    """
    _recover_packing(world_client, ack_mgr, pending_packs, world_id)
    _recover_loading(world_client, ack_mgr, pending_loads, world_id)
    _reset_stuck_loading(world_id)


def _recover_packing(world_client, ack_mgr, pending_packs: dict, world_id: int = None) -> None:
    """Re-issue topack for any shipment stuck in PACKING."""
    stuck = Shipment.objects.filter(
        status=ShipmentStatus.PACKING
    )
    if world_id is not None:
        stuck = stuck.filter(world_id=world_id)
    stuck = stuck.prefetch_related("items__product", "warehouse")

    for shipment in stuck:
        if shipment.shipment_id in {
            pending["shipment_id"]
            for pending in pending_packs.values()
        }:
            continue
        logger.info(
            "reconcile: re-issuing topack for stuck PACKING shipment %s",
            shipment.shipment_id,
        )
        shipment_worker.issue_topack(shipment, world_client, ack_mgr, pending_packs)


def _recover_loading(world_client, ack_mgr, pending_loads: dict, world_id: int = None) -> None:
    """
    Re-issue load for PACKED or TRUCK_ARRIVED shipments that have a truck_id.
    These are shipments where both conditions are satisfied but daemon crashed
    before sending the load command.
    """
    ready_to_load = Shipment.objects.filter(
        status__in=[ShipmentStatus.PACKED, ShipmentStatus.TRUCK_ARRIVED],
        truck_id__isnull=False,
    )
    if world_id is not None:
        ready_to_load = ready_to_load.filter(world_id=world_id)

    for shipment in ready_to_load:
        if shipment.shipment_id in {
            pending["shipment_id"]
            for pending in pending_loads.values()
        }:
            continue
        logger.info(
            "reconcile: re-issuing load for shipment %s (status=%s truck=%d)",
            shipment.shipment_id,
            shipment.status,
            shipment.truck_id,
        )
        shipment_worker.try_issue_load(
            shipment.shipment_id, world_client, ack_mgr, pending_loads
        )


def _reset_stuck_loading(world_id: int = None) -> None:
    """
    Shipments left in LOADING when the daemon crashed: the world may or may
    not have completed the load. Reset them to PACKED and clear the truck so
    an invalid or stale truck_arrived callback cannot cause an infinite load
    retry loop on daemon startup.
    """
    stuck = Shipment.objects.filter(status=ShipmentStatus.LOADING)
    if world_id is not None:
        stuck = stuck.filter(world_id=world_id)

    for shipment in stuck:
        Shipment.objects.filter(
            pk=shipment.pk, status=ShipmentStatus.LOADING
        ).update(status=ShipmentStatus.PACKED, truck_id=None)
        logger.info(
            "reconcile: reset stuck LOADING shipment %s → %s and cleared truck_id",
            shipment.shipment_id,
            ShipmentStatus.PACKED,
        )
