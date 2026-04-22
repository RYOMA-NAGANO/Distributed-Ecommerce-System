from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.views.generic import ListView

from . import auip_states as S
from .models import Package, TrackedShipment

INTEROP_OWNER = "_amazon_interop"


def home(request):
    return render(request, "core/home.html")


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
            # First searcher claims interop-owned shipments. Other users can view
            # search results but cannot persist them into their own shipment list.
            for package in qs:
                if package.user_id == self.request.user.id:
                    TrackedShipment.objects.update_or_create(
                        user=self.request.user,
                        package=package,
                    )
                elif package.user and package.user.username == INTEROP_OWNER:
                    package.user = self.request.user
                    package.save(update_fields=["user"])
                    TrackedShipment.objects.update_or_create(
                        user=self.request.user,
                        package=package,
                    )
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
