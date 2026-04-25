import json
import sys
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "daemon"))

from daemon.shipment_worker import try_issue_load
from store.models import (
    EventSource,
    Order,
    Product,
    Shipment,
    ShipmentEvent,
    ShipmentItem,
    ShipmentStatus,
    Warehouse,
)
from store.services.ups_client import create_shipment


class _AckStub:
    def __init__(self, seqnum: int):
        self._seqnum = int(seqnum)
        self.registered = []

    def next_seqnum(self) -> int:
        return self._seqnum

    def register(self, seqnum, cmd, **_kwargs) -> None:
        self.registered.append((int(seqnum), cmd))


class _WorldClientStub:
    def __init__(self):
        self.sent = []

    def send(self, cmd) -> None:
        self.sent.append(cmd)


class _HttpResponseStub:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b'{"tracking_number":"10001"}'


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
        self.assertIn(77, pending_loads)
        self.assertEqual(pending_loads[77]["shipment_id"], shipment.shipment_id)
        self.assertEqual(len(ack_mgr.registered), 1)
        self.assertEqual(len(world_client.sent), 1)

        cmd = world_client.sent[0]
        self.assertEqual(len(cmd.load), 1)
        load = cmd.load[0]
        self.assertEqual(load.whnum, self.warehouse.warehouse_id)
        self.assertEqual(load.truckid, shipment.truck_id)
        self.assertEqual(load.shipid, int(shipment.shipment_id))
        self.assertEqual(load.seqnum, 77)


class UpsAccountBindingTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="buyer@example.com",
            email="buyer@example.com",
            password="pw",
        )
        self.order = Order.objects.create(
            user=self.user,
            amazon_order_id="ORDER-ACCOUNT-1",
            requested_destination_x=9,
            requested_destination_y=8,
            ups_account="alice@example.com",
        )
        self.warehouse = Warehouse.objects.create(
            world_id=1,
            warehouse_id=1,
            x=2,
            y=4,
        )
        self.shipment = Shipment.objects.create(
            order=self.order,
            warehouse=self.warehouse,
            world_id=1,
            shipment_id="10002",
            tracking_number="10002",
            status=ShipmentStatus.CREATED,
            destination_x=11,
            destination_y=12,
        )
        self.product = Product.objects.create(
            product_id=1,
            name="Box",
            description="box",
            price="1.00",
        )
        ShipmentItem.objects.create(
            shipment=self.shipment,
            product=self.product,
            quantity=1,
            description_snapshot="box",
        )

    @override_settings(UPS_BASE_URL="http://ups.test", UPS_INTEROP_SECRET="")
    def test_create_shipment_sends_order_ups_account(self):
        captured_payload = {}

        def fake_urlopen(req, timeout):
            captured_payload.update(json.loads(req.data.decode("utf-8")))
            return _HttpResponseStub()

        with patch("store.services.ups_client.request.urlopen", side_effect=fake_urlopen):
            create_shipment(self.shipment)

        self.assertEqual(captured_payload["ups_account"], "alice@example.com")

    def test_order_detail_hides_unlinked_ups_account_warning_and_field(self):
        ShipmentEvent.objects.create(
            shipment=self.shipment,
            source=EventSource.WEB,
            event_type="ups_create_shipment",
            world_id=1,
            status_snapshot=ShipmentStatus.CREATED,
            payload={
                "ups_account_email": "alice@example.com",
                "ups_account_linked": False,
                "ups_account_message": (
                    "The UPS account email is not registered with UPS, so this package was not linked to a UPS account."
                ),
            },
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("order_detail", args=[self.order.amazon_order_id]))

        self.assertNotContains(
            response,
            "The UPS account email is not registered with UPS, so this package was not linked to a UPS account.",
        )
        self.assertNotContains(response, "<label>UPS Account</label>", html=True)

    def test_checkout_temporarily_warns_for_unlinked_ups_account(self):
        def fake_create_order_from_product(**_kwargs):
            ShipmentEvent.objects.create(
                shipment=self.shipment,
                source=EventSource.WEB,
                event_type="ups_create_shipment",
                world_id=1,
                status_snapshot=ShipmentStatus.CREATED,
                payload={
                    "ups_account_email": "alice@example.com",
                    "ups_account_linked": False,
                    "ups_account_message": (
                        "The UPS account email is not registered with UPS, so this package was not linked to a UPS account."
                    ),
                },
            )
            return self.order, self.shipment

        self.client.force_login(self.user)
        with patch("store.views.create_order_from_product", side_effect=fake_create_order_from_product):
            response = self.client.post(
                reverse("product_detail", args=["1001"]),
                {
                    "quantity": "1",
                    "destination_x": "11",
                    "destination_y": "12",
                    "ups_account": "alice@example.com",
                },
                follow=True,
            )

        self.assertContains(
            response,
            "The UPS account email is not registered with UPS, so this package was not linked to a UPS account.",
        )

    def test_order_detail_shows_successfully_linked_ups_account(self):
        ShipmentEvent.objects.create(
            shipment=self.shipment,
            source=EventSource.WEB,
            event_type="ups_create_shipment",
            world_id=1,
            status_snapshot=ShipmentStatus.CREATED,
            payload={
                "ups_account_email": "alice@example.com",
                "ups_account_linked": True,
            },
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("order_detail", args=[self.order.amazon_order_id]))

        self.assertContains(response, "<label>UPS Account</label>", html=True)
        self.assertContains(response, "alice@example.com")
