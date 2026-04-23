import json
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from store.models import (
    EventSource,
    HttpDirection,
    HttpIdempotencyRecord,
    Order,
    Product,
    Shipment,
    ShipmentEvent,
    ShipmentItem,
    ShipmentStatus,
    Warehouse,
)
from store.services import order_service
from store.services.ups_client import UpsClientError


class StoreFlowTests(TestCase):
    def setUp(self):
        self.product = Product.objects.create(
            product_id=2001,
            name="Compact Shipping Box Set",
            description="Basic corrugated shipping boxes for project demos and early testing.",
            price=Decimal("24.99"),
            category="Packaging",
            badge="Amazon Lite Choice",
            image_url="https://example.com/box.png",
        )
        self.warehouse = Warehouse.objects.create(
            world_id=1,
            warehouse_id=1,
            x=2,
            y=4,
        )

    def _create_shipment(
        self,
        *,
        status=ShipmentStatus.CREATED,
        truck_id=None,
        shipment_id="17765667628338566",
    ) -> Shipment:
        order = Order.objects.create(
            amazon_order_id=f"ORD-{shipment_id}",
            requested_destination_x=9,
            requested_destination_y=8,
            ups_account="",
        )
        shipment = Shipment.objects.create(
            order=order,
            warehouse=self.warehouse,
            world_id=self.warehouse.world_id,
            shipment_id=shipment_id,
            tracking_number=shipment_id,
            status=status,
            truck_id=truck_id,
            destination_x=9,
            destination_y=8,
        )
        ShipmentItem.objects.create(
            shipment=shipment,
            product=self.product,
            quantity=1,
            description_snapshot=self.product.description[:50],
        )
        return shipment

    def test_product_detail_post_creates_order_and_shipment(self):
        with (
            patch("store.services.order_service.fetch_world_id", return_value=self.warehouse.world_id),
            patch("store.services.order_service._sync_shipment_to_ups") as sync_mock,
            self.captureOnCommitCallbacks(execute=True),
        ):
            response = self.client.post(
                reverse("product_detail", args=[str(self.product.product_id)]),
                data={
                    "quantity": "2",
                    "destination_x": "11",
                    "destination_y": "7",
                    "ups_account": "student-ups",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Shipment.objects.count(), 1)
        self.assertEqual(ShipmentItem.objects.count(), 1)

        shipment = Shipment.objects.select_related("order").get()
        self.assertEqual(shipment.status, ShipmentStatus.CREATED)
        self.assertTrue(shipment.shipment_id.isdigit())
        self.assertEqual(shipment.tracking_number, shipment.shipment_id)
        self.assertEqual(shipment.destination_x, 11)
        self.assertEqual(shipment.destination_y, 7)
        self.assertEqual(shipment.order.ups_account, "student-ups")
        sync_mock.assert_called_once_with(shipment.id)

        creation_event = ShipmentEvent.objects.get(event_type="shipment_created")
        self.assertEqual(creation_event.source, EventSource.WEB)

    def test_default_warehouse_requires_ups_world_binding(self):
        with patch(
            "store.services.order_service.fetch_world_id",
            side_effect=UpsClientError("UPS has not established a World connection yet."),
        ):
            with self.assertRaises(UpsClientError):
                order_service._get_default_warehouse()

    def test_truck_arrived_callback_is_idempotent(self):
        shipment = self._create_shipment(status=ShipmentStatus.PACKED)
        payload = {
            "shipment_id": shipment.shipment_id,
            "truck_id": 5,
            "warehouse_id": self.warehouse.warehouse_id,
            "world_id": self.warehouse.world_id,
        }

        first = self.client.post(
            reverse("truck_arrived"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="truck-arrived-1",
        )
        second = self.client.post(
            reverse("truck_arrived"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="truck-arrived-1",
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertJSONEqual(first.content.decode("utf-8"), second.content.decode("utf-8"))

        shipment.refresh_from_db()
        self.assertEqual(shipment.status, ShipmentStatus.TRUCK_ARRIVED)
        self.assertEqual(shipment.truck_id, 5)
        self.assertEqual(
            ShipmentEvent.objects.filter(shipment=shipment, event_type="truck_arrived").count(),
            1,
        )
        self.assertEqual(
            HttpIdempotencyRecord.objects.filter(
                direction=HttpDirection.INBOUND,
                path="/api/truck-arrived",
            ).count(),
            1,
        )

    def test_load_request_requires_prior_truck_arrival(self):
        shipment = self._create_shipment(status=ShipmentStatus.PACKED, truck_id=None)
        payload = {
            "shipment_id": shipment.shipment_id,
            "truck_id": 7,
            "warehouse_id": self.warehouse.warehouse_id,
            "world_id": self.warehouse.world_id,
        }

        response = self.client.post(
            reverse("load_request"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="load-request-1",
        )

        self.assertEqual(response.status_code, 409)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, ShipmentStatus.PACKED)
        self.assertIsNone(shipment.truck_id)

    def test_out_for_delivery_updates_destination(self):
        shipment = self._create_shipment(status=ShipmentStatus.LOADED, truck_id=5)
        payload = {
            "shipment_id": shipment.shipment_id,
            "truck_id": 5,
            "world_id": self.warehouse.world_id,
            "destination": {"x": 15, "y": 6},
        }

        response = self.client.post(
            reverse("out_for_delivery"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="ofd-1",
        )

        self.assertEqual(response.status_code, 200)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, ShipmentStatus.OUT_FOR_DELIVERY)
        self.assertEqual(shipment.destination_x, 15)
        self.assertEqual(shipment.destination_y, 6)

    def test_delivered_rejects_earlier_states(self):
        shipment = self._create_shipment(status=ShipmentStatus.PACKING, truck_id=5)
        payload = {
            "shipment_id": shipment.shipment_id,
            "truck_id": 5,
            "world_id": self.warehouse.world_id,
        }

        response = self.client.post(
            reverse("delivered"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY="delivered-1",
        )

        self.assertEqual(response.status_code, 409)
        shipment.refresh_from_db()
        self.assertEqual(shipment.status, ShipmentStatus.PACKING)
