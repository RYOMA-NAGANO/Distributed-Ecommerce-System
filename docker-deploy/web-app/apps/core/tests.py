from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from types import SimpleNamespace
from unittest.mock import patch

from . import auip_states as S
from .auip_services import (
    auip_create_shipment,
    auip_mark_ready,
    auip_recover_stuck_loading,
    auip_update_destination,
)
from .models import (
    DestinationUpdate,
    Package,
    PositionUpdate,
    StatusUpdate,
    TrackedShipment,
    Truck,
)
from .views import INTEROP_OWNER


class PackageOwnershipSearchTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.interop, _ = User.objects.get_or_create(
            username=INTEROP_OWNER,
            defaults={"email": "interop@miniups.local", "password": "!"},
        )
        self.alice = User.objects.create_user(
            username="alice",
            email="alice@example.com",
            password="pw",
        )
        self.bob = User.objects.create_user(
            username="bob",
            email="bob@example.com",
            password="pw",
        )

    def create_interop_package(
        self,
        shipment_id="PKG-1",
        amazon_order_id="ORDER-1",
        *,
        world_package_id=None,
        items=None,
    ):
        return Package.objects.create(
            shipment_id=shipment_id,
            world_id=1,
            amazon_order_id=amazon_order_id,
            user=self.interop,
            dest_x=10,
            dest_y=20,
            warehouse_id=1,
            warehouse_x=0,
            warehouse_y=0,
            world_package_id=world_package_id,
            items=items,
            status=S.CREATED,
        )

    def create_owned_package(
        self,
        *,
        user=None,
        status=S.CREATED,
        truck=None,
        delivery_seqnum=None,
        shipment_id="PKG-OWNER-1",
        world_package_id=1001,
    ):
        return Package.objects.create(
            shipment_id=shipment_id,
            world_id=1,
            amazon_order_id=f"ORDER-{shipment_id}",
            user=user or self.alice,
            truck=truck,
            dest_x=10,
            dest_y=20,
            warehouse_id=1,
            warehouse_x=0,
            warehouse_y=0,
            world_package_id=world_package_id,
            delivery_seqnum=delivery_seqnum,
            status=status,
        )

    def test_first_search_claims_interop_package(self):
        package = self.create_interop_package()
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"), {"q": package.shipment_id})

        self.assertEqual(list(response.context["packages"]), [package])
        package.refresh_from_db()
        self.assertEqual(package.user_id, self.alice.id)
        self.assertTrue(
            TrackedShipment.objects.filter(
                user=self.alice,
                package=package,
            ).exists()
        )

    def test_later_search_cannot_steal_claimed_package(self):
        package = self.create_interop_package()
        self.client.force_login(self.alice)
        self.client.get(reverse("my-packages"), {"q": package.shipment_id})

        self.client.force_login(self.bob)
        response = self.client.get(reverse("my-packages"), {"q": package.shipment_id})

        self.assertEqual(list(response.context["packages"]), [])
        package.refresh_from_db()
        self.assertEqual(package.user_id, self.alice.id)
        self.assertFalse(
            TrackedShipment.objects.filter(
                user=self.bob,
                package=package,
            ).exists()
        )

    def test_later_search_does_not_show_claimed_package_by_default(self):
        package = self.create_interop_package()
        self.client.force_login(self.alice)
        self.client.get(reverse("my-packages"), {"q": package.shipment_id})

        self.client.force_login(self.bob)
        self.client.get(reverse("my-packages"), {"q": package.shipment_id})
        response = self.client.get(reverse("my-packages"))

        self.assertEqual(list(response.context["packages"]), [])
        package.refresh_from_db()
        self.assertEqual(package.user_id, self.alice.id)

    def test_claimed_package_appears_without_search(self):
        package = self.create_interop_package()
        self.client.force_login(self.alice)
        self.client.get(reverse("my-packages"), {"q": package.amazon_order_id})

        response = self.client.get(reverse("my-packages"))

        self.assertEqual(list(response.context["packages"]), [package])

    def test_first_search_by_world_package_id_claims_interop_package(self):
        package = self.create_interop_package(world_package_id=88001)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"), {"q": "88001"})

        self.assertEqual(list(response.context["packages"]), [package])
        package.refresh_from_db()
        self.assertEqual(package.user_id, self.alice.id)

    def test_first_search_by_item_product_id_claims_interop_package(self):
        package = self.create_interop_package(
            shipment_id="PKG-PROD-1",
            amazon_order_id="ORDER-PROD-1",
            items=[{"product_id": 1001, "description": "demo", "quantity": 1}],
        )
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"), {"q": "1001"})

        self.assertEqual(list(response.context["packages"]), [package])
        package.refresh_from_db()
        self.assertEqual(package.user_id, self.alice.id)

    def test_later_search_by_same_item_product_id_cannot_steal_claimed_package(self):
        package = self.create_interop_package(
            shipment_id="PKG-PROD-2",
            amazon_order_id="ORDER-PROD-2",
            items=[{"product_id": 1001, "description": "demo", "quantity": 1}],
        )
        self.client.force_login(self.alice)
        self.client.get(reverse("my-packages"), {"q": "1001"})

        self.client.force_login(self.bob)
        response = self.client.get(reverse("my-packages"), {"q": "1001"})

        self.assertEqual(list(response.context["packages"]), [])
        package.refresh_from_db()
        self.assertEqual(package.user_id, self.alice.id)

    def test_owner_can_update_destination_before_loaded(self):
        package = self.create_owned_package(status=S.PACKED)
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("package-destination-update", args=[package.shipment_id]),
            {"dest_x": "30", "dest_y": "40"},
        )

        self.assertEqual(response.status_code, 302)
        package.refresh_from_db()
        self.assertEqual((package.dest_x, package.dest_y), (30, 40))
        self.assertEqual(package.status, S.PACKED)
        self.assertIsNone(package.delivery_seqnum)
        self.assertTrue(
            DestinationUpdate.objects.filter(
                shipment=package,
                x=30,
                y=40,
            ).exists()
        )

    def test_owner_destination_update_appends_history_record(self):
        package = self.create_owned_package(status=S.PACKED)
        DestinationUpdate.objects.create(
            shipment=package,
            x=package.dest_x,
            y=package.dest_y,
            update_time=1,
        )
        self.client.force_login(self.alice)

        self.client.post(
            reverse("package-destination-update", args=[package.shipment_id]),
            {"dest_x": "31", "dest_y": "41"},
        )

        self.assertEqual(
            list(
                DestinationUpdate.objects.filter(shipment=package)
                .order_by("id")
                .values_list("x", "y")
            ),
            [(10, 20), (31, 41)],
        )

    def test_owner_update_loaded_package_requeues_delivery_to_same_truck(self):
        truck = Truck.objects.create(
            truck_id=7,
            truck_status=Truck.TruckStatus.DELIVERING,
        )
        package = self.create_owned_package(
            status=S.OUT_FOR_DELIVERY,
            truck=truck,
            delivery_seqnum=99,
        )
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("package-destination-update", args=[package.shipment_id]),
            {"dest_x": "50", "dest_y": "60"},
        )

        self.assertEqual(response.status_code, 302)
        package.refresh_from_db()
        self.assertEqual((package.dest_x, package.dest_y), (50, 60))
        self.assertEqual(package.status, S.OUT_FOR_DELIVERY)
        self.assertEqual(package.truck_id, truck.truck_id)
        self.assertIsNone(package.delivery_seqnum)

    def test_non_owner_cannot_update_destination(self):
        package = self.create_owned_package(user=self.alice)
        self.client.force_login(self.bob)

        response = self.client.post(
            reverse("package-destination-update", args=[package.shipment_id]),
            {"dest_x": "30", "dest_y": "40"},
        )

        self.assertEqual(response.status_code, 403)
        package.refresh_from_db()
        self.assertEqual((package.dest_x, package.dest_y), (10, 20))

    def test_delivered_package_cannot_update_destination(self):
        package = self.create_owned_package(status=S.DELIVERED)
        self.client.force_login(self.alice)

        response = self.client.post(
            reverse("package-destination-update", args=[package.shipment_id]),
            {"dest_x": "30", "dest_y": "40"},
        )

        self.assertEqual(response.status_code, 302)
        package.refresh_from_db()
        self.assertEqual((package.dest_x, package.dest_y), (10, 20))

    def test_non_owner_search_result_has_no_destination_form(self):
        package = self.create_owned_package(user=self.alice)
        self.client.force_login(self.bob)

        response = self.client.get(reverse("my-packages"), {"q": package.shipment_id})

        self.assertEqual(list(response.context["packages"]), [])
        self.assertNotContains(response, "Edit destination")
        self.assertContains(response, "No shipments matched your search.")

    def test_owner_package_result_has_destination_edit_button(self):
        package = self.create_owned_package(user=self.alice)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"))

        self.assertContains(response, "Edit destination")
        self.assertContains(response, "View details")
        self.assertContains(response, reverse("package-destination-update", args=[package.shipment_id]))

    def test_non_owner_search_result_cannot_view_details(self):
        package = self.create_owned_package(user=self.alice)
        PositionUpdate.objects.create(shipment=package, x=1, y=2, update_time=20)
        DestinationUpdate.objects.create(shipment=package, x=3, y=4, update_time=10)
        self.client.force_login(self.bob)

        response = self.client.get(reverse("my-packages"), {"q": package.shipment_id})

        self.assertNotContains(response, "View details")
        self.assertNotContains(response, "Destination updated to (3, 4)")
        self.assertNotContains(response, "Position updated to (1, 2)")
        self.assertEqual(list(response.context["packages"]), [])

    @patch("apps.core.views._fetch_live_truck_position")
    def test_owner_live_position_endpoint_returns_world_coordinates(self, mock_live_lookup):
        truck = Truck.objects.create(
            truck_id=41,
            truck_status=Truck.TruckStatus.TRAVELING,
        )
        package = self.create_owned_package(user=self.alice, truck=truck, shipment_id="PKG-LIVE-1")
        mock_live_lookup.return_value = {"x": 55, "y": 66}
        self.client.force_login(self.alice)

        response = self.client.get(reverse("package-live-position", args=[package.shipment_id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual((payload["x"], payload["y"]), (55, 66))
        self.assertEqual(payload["truck_id"], truck.truck_id)

    @patch("apps.core.views._fetch_live_truck_position")
    def test_non_owner_live_position_endpoint_is_hidden(self, mock_live_lookup):
        package = self.create_owned_package(user=self.alice, shipment_id="PKG-LIVE-2")
        self.client.force_login(self.bob)

        response = self.client.get(reverse("package-live-position", args=[package.shipment_id]))

        self.assertEqual(response.status_code, 404)
        mock_live_lookup.assert_not_called()

    def test_auip_create_records_initial_destination(self):
        package = auip_create_shipment(
            {
                "shipment_id": "PKG-AUIP-1",
                "world_id": 1,
                "amazon_order_id": "ORDER-AUIP-1",
                "warehouse": {"id": 1, "x": 0, "y": 0},
                "destination": {"x": 70, "y": 80},
                "items": [{"product_id": 1, "description": "box", "quantity": 1}],
            }
        )

        self.assertEqual(
            list(DestinationUpdate.objects.filter(shipment=package).values_list("x", "y")),
            [(70, 80)],
        )

    def test_auip_create_records_initial_status(self):
        package = auip_create_shipment(
            {
                "shipment_id": "PKG-AUIP-STATUS-1",
                "world_id": 1,
                "amazon_order_id": "ORDER-AUIP-STATUS-1",
                "warehouse": {"id": 1, "x": 0, "y": 0},
                "destination": {"x": 70, "y": 80},
                "items": [{"product_id": 1, "description": "box", "quantity": 1}],
            }
        )

        self.assertEqual(
            list(StatusUpdate.objects.filter(shipment=package).values_list("status", flat=True)),
            [S.CREATED],
        )

    def test_auip_destination_update_appends_history_record(self):
        package = auip_create_shipment(
            {
                "shipment_id": "PKG-AUIP-2",
                "world_id": 1,
                "amazon_order_id": "ORDER-AUIP-2",
                "warehouse": {"id": 1, "x": 0, "y": 0},
                "destination": {"x": 70, "y": 80},
                "items": [{"product_id": 1, "description": "box", "quantity": 1}],
            }
        )

        auip_update_destination(package.shipment_id, 71, 81, "customer_redirect")

        self.assertEqual(
            list(
                DestinationUpdate.objects.filter(shipment=package)
                .order_by("id")
                .values_list("x", "y")
            ),
            [(70, 80), (71, 81)],
        )
        self.assertEqual(
            list(
                StatusUpdate.objects.filter(shipment=package)
                .order_by("id")
                .values_list("status", flat=True)
            ),
            [S.CREATED, S.UPDATED],
        )

    def test_mark_ready_records_package_position_at_warehouse(self):
        package = self.create_owned_package(status=S.CREATED)

        auip_mark_ready(package.shipment_id, package.warehouse_id, package.world_id)

        self.assertEqual(
            list(PositionUpdate.objects.filter(shipment=package).values_list("x", "y")),
            [(package.warehouse_x, package.warehouse_y)],
        )

    def test_world_completion_records_position_for_all_packages_on_truck(self):
        from apps.interop.management.commands.run_ups_daemon import Command

        truck = Truck.objects.create(
            truck_id=9,
            truck_status=Truck.TruckStatus.DELIVERING,
        )
        package_a = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-POS-1",
            status=S.OUT_FOR_DELIVERY,
        )
        package_b = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-POS-2",
            status=S.OUT_FOR_DELIVERY,
            world_package_id=1002,
        )
        command = Command()
        command._current_world_id = 1
        finished = SimpleNamespace(
            status="idle",
            truckid=truck.truck_id,
            x=33,
            y=44,
            seqnum=123,
        )

        with patch("apps.interop.management.commands.run_ups_daemon.amazon_client.notify_truck_arrived"):
            command._handle_u_finished(finished)

        self.assertEqual(
            set(PositionUpdate.objects.values_list("shipment_id", "x", "y")),
            {
                (package_a.shipment_id, 33, 44),
                (package_b.shipment_id, 33, 44),
            },
        )

    def test_recover_stuck_loading_requeues_package_when_truck_is_idle(self):
        truck = Truck.objects.create(
            truck_id=12,
            truck_status=Truck.TruckStatus.IDLE,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-STUCK-LOAD-1",
            status=S.LOADING,
            world_package_id=1003,
        )

        updated = auip_recover_stuck_loading(world_id=package.world_id)

        self.assertEqual(updated, 1)
        package.refresh_from_db()
        self.assertEqual(package.status, S.PACKED)
        self.assertIsNone(package.truck_id)
        self.assertEqual(
            list(
                StatusUpdate.objects.filter(shipment=package)
                .order_by("id")
                .values_list("status", flat=True)
            ),
            [S.PACKED],
        )
