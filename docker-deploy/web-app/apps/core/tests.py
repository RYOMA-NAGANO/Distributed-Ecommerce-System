from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import auip_states as S
from .models import DestinationUpdate, Package, TrackedShipment, Truck
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

    def create_interop_package(self, shipment_id="PKG-1", amazon_order_id="ORDER-1"):
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
            world_package_id=1001,
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

        self.assertEqual(list(response.context["packages"]), [package])
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

        self.assertContains(response, package.shipment_id)
        self.assertNotContains(response, "Edit destination")

    def test_owner_package_result_has_destination_edit_button(self):
        package = self.create_owned_package(user=self.alice)
        self.client.force_login(self.alice)

        response = self.client.get(reverse("my-packages"))

        self.assertContains(response, "Edit destination")
        self.assertContains(response, reverse("package-destination-update", args=[package.shipment_id]))
