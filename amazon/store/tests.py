import sys
from pathlib import Path

from django.test import TestCase

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daemon"))

from daemon.shipment_worker import try_issue_load
from store.models import Order, Shipment, ShipmentStatus, Warehouse


class _AckStub:
    def __init__(self, seqnum: int):
        self._seqnum = int(seqnum)
        self.registered = []

    def next_seqnum(self) -> int:
        return self._seqnum

    def register(self, seqnum, cmd) -> None:
        self.registered.append((int(seqnum), cmd))


class _WorldClientStub:
    def __init__(self):
        self.sent = []

    def send(self, cmd) -> None:
        self.sent.append(cmd)


class ShipmentWorkerLoadRetryTests(TestCase):
    def setUp(self):
        self.order = Order.objects.create(
            amazon_order_id="ORDER-LOAD-1",
            requested_destination_x=9,
            requested_destination_y=8,
            ups_account="alice",
        )
        self.warehouse = Warehouse.objects.create(
            world_id=1,
            warehouse_id=1,
            x=2,
            y=4,
        )

    def test_try_issue_load_reissues_world_load_for_loading_shipment(self):
        shipment = Shipment.objects.create(
            order=self.order,
            warehouse=self.warehouse,
            world_id=1,
            shipment_id="10001",
            tracking_number="10001",
            status=ShipmentStatus.LOADING,
            truck_id=7,
            destination_x=11,
            destination_y=12,
        )
        world_client = _WorldClientStub()
        ack_mgr = _AckStub(seqnum=77)
        pending_loads = {}

        issued = try_issue_load(
            shipment.shipment_id,
            world_client,
            ack_mgr,
            pending_loads,
        )

        self.assertTrue(issued)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, ShipmentStatus.LOADING)
        self.assertEqual(pending_loads, {77: shipment.shipment_id})
        self.assertEqual(len(ack_mgr.registered), 1)
        self.assertEqual(len(world_client.sent), 1)

        cmd = world_client.sent[0]
        self.assertEqual(len(cmd.load), 1)
        load = cmd.load[0]
        self.assertEqual(load.whnum, self.warehouse.warehouse_id)
        self.assertEqual(load.truckid, shipment.truck_id)
        self.assertEqual(load.shipid, int(shipment.shipment_id))
        self.assertEqual(load.seqnum, 77)

