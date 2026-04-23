from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from . import auip_states as S
from .models import Package, TrackedShipment
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

    def test_claimed_package_appears_without_search(self):
        package = self.create_interop_package()
        self.client.force_login(self.alice)
        self.client.get(reverse("my-packages"), {"q": package.amazon_order_id})

        response = self.client.get(reverse("my-packages"))

        self.assertEqual(list(response.context["packages"]), [package])
