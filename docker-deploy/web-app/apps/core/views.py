from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render
from django.views.generic import ListView

from . import auip_states as S
from .models import Package, TrackedShipment

INTEROP_OWNER = "_amazon_interop"


def home(request):
    return render(request, "core/home.html")


def claim_search_results_for_user(search_qs, user):
    """
    Amazon-created shipments start owned by the interop placeholder user.
    The first real user who searches a matching package atomically claims it.
    """
    interop_owner_id = (
        get_user_model()
        .objects.filter(username=INTEROP_OWNER)
        .values_list("id", flat=True)
        .first()
    )
    if interop_owner_id is None:
        return

    with transaction.atomic():
        claimable_ids = list(
            search_qs.filter(user_id=interop_owner_id).values_list(
                "shipment_id",
                flat=True,
            )
        )
        if claimable_ids:
            Package.objects.filter(
                shipment_id__in=claimable_ids,
                user_id=interop_owner_id,
            ).update(user_id=user.id)

        owned_ids = list(
            search_qs.filter(user_id=user.id).values_list("shipment_id", flat=True)
        )
        for shipment_id in owned_ids:
            TrackedShipment.objects.update_or_create(
                user=user,
                package_id=shipment_id,
            )


class PackageListView(LoginRequiredMixin, ListView):
    model = Package
    template_name = "core/packages.html"
    context_object_name = "packages"

    def get_queryset(self):
        q = (self.request.GET.get("q") or "").strip()
        qs = Package.objects.select_related("truck", "user")
        tab = (self.request.GET.get("tab") or "all").lower()

        if q:
            qs = qs.filter(
                Q(shipment_id__icontains=q) | Q(amazon_order_id__icontains=q)
            )
            claim_search_results_for_user(qs, self.request.user)
            qs = qs.filter(user=self.request.user)
        else:
            qs = qs.filter(user=self.request.user)

        if tab == "active":
            qs = qs.exclude(status__in=[S.DELIVERED, S.CANCELED, S.DELIVERY_FAILED])
        elif tab == "delivered":
            qs = qs.filter(status=S.DELIVERED)

        return qs.order_by("shipment_id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tab"] = (self.request.GET.get("tab") or "all").lower()
        ctx["search_q"] = (self.request.GET.get("q") or "").strip()
        return ctx
