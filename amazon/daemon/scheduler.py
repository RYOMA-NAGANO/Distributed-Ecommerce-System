import logging
import time
import threading

from store.models import EventSource, Shipment, ShipmentEvent, ShipmentStatus
from world_amazon_pb2 import ACommands
import inventory_worker
import shipment_worker

logger = logging.getLogger(__name__)

POLL_INTERVAL = 3  # seconds


class Scheduler:
    """
    Central state machine loop.

    Responsibilities:
    - Poll DB for new shipments and drive them through the pipeline.
    - Dispatch world simulator responses to the right worker.
    - Notify UPS (via ups_notify callback) when key transitions happen.

    ups_notify(event, shipment_id) where event is one of:
        'shipment_created', 'packed', 'loaded'
    """

    def __init__(self, world_client, ack_mgr, ups_notify=None, world_id=None):
        self._world = world_client
        self._ack = ack_mgr
        self._ups_notify = ups_notify or (lambda event, sid: None)
        self._world_id = world_id

        self._pending_buys = {}    # seqnum -> buy metadata (shipment_id, warehouse_id, items)
        self._pending_packs = {}   # seqnum -> shipment_id
        self._pending_loads = {}   # seqnum -> shipment_id
        self._processed_world_seqnums = set()

        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, name="scheduler", daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #
    # World response dispatcher — called from WorldClient's recv thread   #
    # ------------------------------------------------------------------ #

    def on_world_response(self, resp):
        # Process acks first.
        self._ack.ack_many(resp.acks)
        world_response_acks = []
        if (
            resp.acks
            or resp.arrived
            or resp.ready
            or resp.loaded
            or resp.error
            or resp.packagestatus
        ):
            logger.info(
                "world resp: acks=%d arrived=%d ready=%d loaded=%d errors=%d packagestatus=%d",
                len(resp.acks),
                len(resp.arrived),
                len(resp.ready),
                len(resp.loaded),
                len(resp.error),
                len(resp.packagestatus),
            )
        ready_from_buy_acks = inventory_worker.handle_buy_acks(
            resp.acks,
            self._pending_buys,
            self._world_id,
        )
        for sid in ready_from_buy_acks:
            self._advance_to_packing(sid)

        for arrived in resp.arrived:
            world_response_acks.append(arrived.seqnum)
            if self._already_processed(arrived.seqnum):
                continue
            logger.info(
                "world arrived: wh=%s seq=%s products=%s",
                arrived.whnum,
                arrived.seqnum,
                [thing.id for thing in arrived.things],
            )

            ready_ids = inventory_worker.handle_arrived(arrived, self._pending_buys, self._world_id)
            for sid in ready_ids:
                self._advance_to_packing(sid)

        for packed in resp.ready:
            world_response_acks.append(packed.seqnum)
            if self._already_processed(packed.seqnum):
                continue

            sid = shipment_worker.handle_ready(packed, self._pending_packs)
            if sid:
                shipment_worker.try_issue_load(sid, self._world, self._ack, self._pending_loads)
                self._ups_notify("packed", sid)

        for loaded in resp.loaded:
            world_response_acks.append(loaded.seqnum)
            if self._already_processed(loaded.seqnum):
                continue

            sid = shipment_worker.handle_loaded(loaded, self._pending_loads)
            if sid:
                self._ups_notify("loaded", sid)

        for err in resp.error:
            world_response_acks.append(err.seqnum)
            if self._already_processed(err.seqnum):
                continue

            self._ack.ack(err.originseqnum)
            self._pending_buys.pop(err.originseqnum, None)
            self._pending_packs.pop(err.originseqnum, None)

            failed_load_shipment_id = self._pending_loads.pop(err.originseqnum, None)
            if failed_load_shipment_id:
                self._handle_failed_load(failed_load_shipment_id, err.err)

            logger.error("World error seqnum=%d: %s", err.originseqnum, err.err)

        for package in resp.packagestatus:
            world_response_acks.append(package.seqnum)
            self._processed_world_seqnums.add(package.seqnum)

        self._send_world_acks(world_response_acks)

    # ------------------------------------------------------------------ #
    # Poll loop                                                            #
    # ------------------------------------------------------------------ #

    def _poll_loop(self):
        while self._running:
            try:
                inventory_worker.process_created_shipments(
                    self._world, self._ack, self._pending_buys, self._world_id
                )
                self._retry_packing()
                self._retry_loading()
            except Exception as exc:
                logger.error("Scheduler poll error: %s", exc)
            time.sleep(POLL_INTERVAL)

    def _retry_packing(self):
        """Re-issue topack for PACKING shipments not yet in pending_packs."""
        in_flight = set(self._pending_packs.values())
        shipments = Shipment.objects.filter(status=ShipmentStatus.PACKING)
        if self._world_id is not None:
            shipments = shipments.filter(world_id=self._world_id)
        for shipment in shipments:
            if shipment.shipment_id not in in_flight:
                shipment_worker.issue_topack(
                    shipment, self._world, self._ack, self._pending_packs
                )

    def _advance_to_packing(self, shipment_id: str):
        """Re-check inventory and issue topack if stock is now sufficient."""
        try:
            shipments = Shipment.objects.filter(shipment_id=shipment_id)
            if self._world_id is not None:
                shipments = shipments.filter(world_id=self._world_id)
            shipment = shipments.get()
        except Shipment.DoesNotExist:
            return
        if shipment.status == ShipmentStatus.CREATED:
            inventory_worker._handle_created(
                shipment, self._world, self._ack, self._pending_buys
            )
        if shipment.status == ShipmentStatus.PACKING:
            shipment_worker.issue_topack(
                shipment, self._world, self._ack, self._pending_packs
            )

    def _retry_loading(self):
        in_flight = set(self._pending_loads.values())
        candidates = Shipment.objects.filter(
            status__in=[
                ShipmentStatus.PACKED,
                ShipmentStatus.TRUCK_ARRIVED,
                ShipmentStatus.LOADING,
            ],
            truck_id__isnull=False,
        )
        if self._world_id is not None:
            candidates = candidates.filter(world_id=self._world_id)

        for shipment in candidates:
            if shipment.shipment_id in in_flight:
                continue
            shipment_worker.try_issue_load(
                shipment.shipment_id,
                self._world,
                self._ack,
                self._pending_loads,
            )

    def _already_processed(self, seqnum: int) -> bool:
        if seqnum in self._processed_world_seqnums:
            return True

        self._processed_world_seqnums.add(seqnum)
        return False

    def _send_world_acks(self, seqnums):
        unique_seqnums = []
        seen = set()
        for seqnum in seqnums:
            if seqnum and seqnum not in seen:
                unique_seqnums.append(seqnum)
                seen.add(seqnum)

        if not unique_seqnums:
            return

        cmd = ACommands()
        cmd.acks.extend(unique_seqnums)
        self._world.send(cmd)

    def _handle_failed_load(self, shipment_id: str, error_message: str):
        try:
            shipments = Shipment.objects.filter(shipment_id=shipment_id)
            if self._world_id is not None:
                shipments = shipments.filter(world_id=self._world_id)
            shipment = shipments.get()
        except Shipment.DoesNotExist:
            return

        if shipment.status == ShipmentStatus.LOADING:
            shipment.status = (
                ShipmentStatus.TRUCK_ARRIVED
                if shipment.truck_id is not None
                else ShipmentStatus.PACKED
            )
            shipment.save(update_fields=["status", "updated_at"])

        ShipmentEvent.objects.create(
            shipment=shipment,
            source=EventSource.WORLD,
            event_type="load_failed",
            world_id=shipment.world_id,
            status_snapshot=shipment.status,
            payload={"detail": error_message},
            error_message=error_message,
        )
