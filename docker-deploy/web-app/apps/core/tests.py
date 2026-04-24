from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from types import SimpleNamespace
from unittest.mock import patch

from . import auip_states as S
from .auip_services import (
    auip_create_shipment,
    auip_confirm_loaded,
    auip_mark_ready,
    auip_recover_stale_delivery_requests,
    auip_recover_stuck_loading,
    auip_try_send_load_request_and_loading,
    auip_try_send_load_request_when_possible,
    auip_update_destination,
    update_destination_for_owner,
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
from apps.interop.models import WorldBinding


@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="noreply@miniups.test",
)
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

    def test_world_binding_endpoint_returns_current_connected_world(self):
        WorldBinding.objects.create(id=1, world_id=42, result="connected!")

        response = self.client.get(
            reverse("auip-world-binding"),
            HTTP_AUTHORIZATION="Bearer mini-ups-shared-secret",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["world_id"], 42)

    def test_world_binding_endpoint_hides_rejected_binding(self):
        WorldBinding.objects.create(
            id=1,
            world_id=1,
            result="error",
        )

        response = self.client.get(
            reverse("auip-world-binding"),
            HTTP_AUTHORIZATION="Bearer mini-ups-shared-secret",
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error_code"], "WORLD_NOT_READY")

    @override_settings(WORLD_ID="")
    def test_world_connect_message_initializes_three_default_trucks(self):
        from apps.interop.services.world_client import build_connect_message

        Truck.objects.all().delete()

        message = build_connect_message()

        self.assertEqual(
            [(truck.id, truck.x, truck.y) for truck in message.trucks],
            [(1, 1, 1), (2, 5, 1), (3, 9, 1)],
        )
        self.assertEqual(
            list(Truck.objects.order_by("truck_id").values_list("truck_id", "truck_status")),
            [
                (1, Truck.TruckStatus.IDLE),
                (2, Truck.TruckStatus.IDLE),
                (3, Truck.TruckStatus.IDLE),
            ],
        )

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

    def test_owner_package_uses_latest_recorded_position_for_map(self):
        package = self.create_owned_package(user=self.alice, shipment_id="PKG-LIVE-1")
        PositionUpdate.objects.create(shipment=package, x=1, y=2, update_time=20)
        PositionUpdate.objects.create(shipment=package, x=55, y=66, update_time=30)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"))

        self.assertEqual(response.status_code, 200)
        rendered = response.context["packages"][0]
        self.assertEqual((rendered.current_position_x, rendered.current_position_y), (55, 66))
        self.assertContains(response, "Position updated to (55, 66)")
        self.assertNotContains(response, "data-live-url")
        self.assertNotContains(response, "live-position")

    def test_delivered_package_uses_destination_instead_of_latest_position(self):
        package = self.create_owned_package(
            user=self.alice,
            shipment_id="PKG-LIVE-2",
            status=S.DELIVERED,
        )
        PositionUpdate.objects.create(shipment=package, x=55, y=66, update_time=30)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"))

        self.assertEqual(response.status_code, 200)
        rendered = response.context["packages"][0]
        self.assertEqual(
            (rendered.current_position_x, rendered.current_position_y),
            (package.dest_x, package.dest_y),
        )

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

    def test_mark_ready_emails_owner_when_package_is_packed(self):
        package = self.create_owned_package(status=S.CREATED)

        with self.captureOnCommitCallbacks(execute=True):
            auip_mark_ready(package.shipment_id, package.warehouse_id, package.world_id)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alice.email])
        self.assertIn("packed", mail.outbox[0].subject.lower())
        self.assertIn(package.shipment_id, mail.outbox[0].body)

    def test_mark_ready_emails_owner_when_truck_already_arrived(self):
        package = self.create_owned_package(status=S.TRUCK_ARRIVED)

        with self.captureOnCommitCallbacks(execute=True):
            auip_mark_ready(package.shipment_id, package.warehouse_id, package.world_id)

        package.refresh_from_db()
        self.assertEqual(package.status, S.TRUCK_ARRIVED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("packed", mail.outbox[0].subject.lower())

    def test_mark_ready_does_not_send_duplicate_packed_email(self):
        package = self.create_owned_package(status=S.TRUCK_ARRIVED)
        StatusUpdate.objects.create(shipment=package, status=S.PACKED, update_time=1)

        with self.captureOnCommitCallbacks(execute=True):
            auip_mark_ready(package.shipment_id, package.warehouse_id, package.world_id)

        self.assertEqual(len(mail.outbox), 0)

    def test_confirm_loaded_emails_owner_when_package_is_loaded(self):
        truck = Truck.objects.create(
            truck_id=16,
            truck_status=Truck.TruckStatus.LOADING,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-EMAIL-LOADED",
            status=S.LOADING,
        )

        with self.captureOnCommitCallbacks(execute=True):
            auip_confirm_loaded(
                package.shipment_id,
                truck.truck_id,
                package.warehouse_id,
                package.world_id,
            )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alice.email])
        self.assertIn("loaded", mail.outbox[0].subject.lower())

    def test_load_request_loaded_response_marks_package_loaded(self):
        truck = Truck.objects.create(
            truck_id=18,
            truck_status=Truck.TruckStatus.LOADING,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-LOAD-RECONCILE",
            status=S.TRUCK_ARRIVED,
        )

        with patch(
            "apps.core.auip_services.amazon_client.notify_load_request",
            return_value={"status": S.LOADED},
        ):
            with self.captureOnCommitCallbacks(execute=True):
                auip_try_send_load_request_and_loading(package)

        package.refresh_from_db()
        self.assertEqual(package.status, S.LOADED)
        self.assertEqual(
            list(
                StatusUpdate.objects.filter(shipment=package)
                .order_by("id")
                .values_list("status", flat=True)
            ),
            [S.LOADED],
        )
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("loaded", mail.outbox[0].subject.lower())

    def test_try_send_load_request_requires_truck_arrived_status(self):
        truck = Truck.objects.create(
            truck_id=181,
            truck_status=Truck.TruckStatus.ARRIVE_WAREHOUSE,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-LOAD-GUARD",
            status=S.PACKED,
        )

        with patch("apps.core.auip_services.amazon_client.notify_load_request") as notify_mock:
            sent = auip_try_send_load_request_when_possible(package.shipment_id)

        package.refresh_from_db()
        self.assertFalse(sent)
        self.assertEqual(package.status, S.PACKED)
        notify_mock.assert_not_called()

    def test_try_send_load_request_sends_after_truck_arrived(self):
        truck = Truck.objects.create(
            truck_id=182,
            truck_status=Truck.TruckStatus.ARRIVE_WAREHOUSE,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-LOAD-TRUCK-ARRIVED",
            status=S.TRUCK_ARRIVED,
        )

        with patch(
            "apps.core.auip_services.amazon_client.notify_load_request",
            return_value={"status": S.LOADING},
        ) as notify_mock:
            sent = auip_try_send_load_request_when_possible(package.shipment_id)

        package.refresh_from_db()
        self.assertTrue(sent)
        self.assertEqual(package.status, S.LOADING)
        notify_mock.assert_called_once()

    def test_destination_update_emails_owner(self):
        package = self.create_owned_package(status=S.PACKED)

        with self.captureOnCommitCallbacks(execute=True):
            update_destination_for_owner(package.shipment_id, self.alice, 91, 92)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alice.email])
        self.assertIn("destination", mail.outbox[0].subject.lower())
        self.assertIn("(91, 92)", mail.outbox[0].body)

    def test_delivery_made_emails_owner_when_package_is_delivered(self):
        from apps.interop.management.commands.run_ups_daemon import Command

        truck = Truck.objects.create(
            truck_id=17,
            truck_status=Truck.TruckStatus.DELIVERING,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-EMAIL-DELIVERED",
            status=S.OUT_FOR_DELIVERY,
            world_package_id=1006,
        )
        command = Command()
        command._current_world_id = 1
        delivered = SimpleNamespace(
            packageid=package.world_package_id,
            truckid=truck.truck_id,
            seqnum=456,
        )

        with patch("apps.interop.management.commands.run_ups_daemon.amazon_client.notify_delivered"):
            with self.captureOnCommitCallbacks(execute=True):
                command._handle_u_delivery_made(delivered)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alice.email])
        self.assertIn("delivered", mail.outbox[0].subject.lower())

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

    def test_world_position_recording_skips_delivered_packages(self):
        from apps.interop.management.commands.run_ups_daemon import Command

        truck = Truck.objects.create(
            truck_id=10,
            truck_status=Truck.TruckStatus.DELIVERING,
        )
        active_package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-POS-ACTIVE",
            status=S.OUT_FOR_DELIVERY,
        )
        delivered_package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-POS-DELIVERED",
            status=S.DELIVERED,
            world_package_id=1002,
        )
        command = Command()
        command._current_world_id = 1

        command._record_truck_package_positions(truck.truck_id, 77, 88)

        self.assertEqual(
            set(PositionUpdate.objects.values_list("shipment_id", "x", "y")),
            {
                (active_package.shipment_id, 77, 88),
            },
        )
        self.assertFalse(
            PositionUpdate.objects.filter(shipment=delivered_package).exists()
        )

    def test_world_position_recording_skips_unchanged_coordinates(self):
        from apps.interop.management.commands.run_ups_daemon import Command

        truck = Truck.objects.create(
            truck_id=11,
            truck_status=Truck.TruckStatus.DELIVERING,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-POS-DEDUP",
            status=S.OUT_FOR_DELIVERY,
        )
        command = Command()
        command._current_world_id = 1

        command._record_truck_package_positions(truck.truck_id, 77, 88)
        command._record_truck_package_positions(truck.truck_id, 77, 88)
        command._record_truck_package_positions(truck.truck_id, 78, 88)

        self.assertEqual(
            list(
                PositionUpdate.objects.filter(shipment=package)
                .order_by("id")
                .values_list("x", "y")
            ),
            [(77, 88), (78, 88)],
        )

    def test_delivery_waits_until_same_truck_finishes_warehouse_loading(self):
        from apps.interop.management.commands.run_ups_daemon import Command

        truck = Truck.objects.create(
            truck_id=13,
            truck_status=Truck.TruckStatus.ARRIVE_WAREHOUSE,
        )
        self.create_owned_package(
            truck=truck,
            shipment_id="PKG-STILL-LOADING",
            status=S.LOADING,
        )
        loaded = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-READY-DELIVERY",
            status=S.LOADED,
            world_package_id=1004,
        )
        command = Command()
        command._current_world_id = 1
        send_deliver = lambda *args, **kwargs: self.fail("delivery should not be dispatched")

        command._enqueue_deliveries(None, send_deliver)

        loaded.refresh_from_db()
        truck.refresh_from_db()
        self.assertIsNone(loaded.delivery_seqnum)
        self.assertEqual(loaded.status, S.LOADED)
        self.assertEqual(truck.truck_status, Truck.TruckStatus.ARRIVE_WAREHOUSE)

    def test_pickup_selection_skips_truck_waiting_for_warehouse_loading(self):
        from apps.interop.management.commands.run_ups_daemon import Command

        truck = Truck.objects.create(
            truck_id=14,
            truck_status=Truck.TruckStatus.ARRIVE_WAREHOUSE,
        )
        Truck.objects.exclude(truck_id=truck.truck_id).update(truck_status=Truck.TruckStatus.INVALID)
        self.create_owned_package(
            truck=truck,
            shipment_id="PKG-BLOCK-PICKUP",
            status=S.TRUCK_ARRIVED,
        )
        command = Command()
        command._current_world_id = 1

        self.assertIsNone(command._select_dispatchable_pickup_truck())

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

    def test_recover_stuck_truck_arrived_requeues_package_when_truck_is_idle(self):
        truck = Truck.objects.create(
            truck_id=15,
            truck_status=Truck.TruckStatus.IDLE,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-STUCK-ARRIVED-1",
            status=S.TRUCK_ARRIVED,
            world_package_id=1005,
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

    def test_recover_stale_delivery_requeues_when_truck_is_idle(self):
        truck = Truck.objects.create(
            truck_id=16,
            truck_status=Truck.TruckStatus.IDLE,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-STUCK-DELIVERY-1",
            status=S.OUT_FOR_DELIVERY,
            world_package_id=1007,
            delivery_seqnum=555,
        )

        updated = auip_recover_stale_delivery_requests(world_id=package.world_id)

        self.assertEqual(updated, 1)
        package.refresh_from_db()
        self.assertEqual(package.status, S.OUT_FOR_DELIVERY)
        self.assertEqual(package.truck_id, truck.truck_id)
        self.assertIsNone(package.delivery_seqnum)

    def test_recover_stale_delivery_keeps_active_delivery_in_flight(self):
        truck = Truck.objects.create(
            truck_id=17,
            truck_status=Truck.TruckStatus.DELIVERING,
        )
        package = self.create_owned_package(
            truck=truck,
            shipment_id="PKG-STUCK-DELIVERY-2",
            status=S.OUT_FOR_DELIVERY,
            world_package_id=1008,
            delivery_seqnum=556,
        )

        updated = auip_recover_stale_delivery_requests(world_id=package.world_id)

        self.assertEqual(updated, 0)
        package.refresh_from_db()
        self.assertEqual(package.delivery_seqnum, 556)
