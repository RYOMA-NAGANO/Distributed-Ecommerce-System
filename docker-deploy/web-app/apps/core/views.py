from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.shortcuts import render
from django.views.generic import ListView

from . import auip_states as S
from .models import Package


def home(request):
    return render(request, "core/home.html")


class PackageListView(LoginRequiredMixin, ListView):
    model = Package
    template_name = "core/packages.html"
    context_object_name = "packages"

    def get_queryset(self):
        # AUIP integration view: search/list shipments globally by identifiers.
        qs = Package.objects.select_related("truck", "user")
        tab = (self.request.GET.get("tab") or "all").lower()
        if tab == "active":
            qs = qs.exclude(status__in=[S.DELIVERED, S.CANCELED, S.DELIVERY_FAILED])
        elif tab == "delivered":
            qs = qs.filter(status=S.DELIVERED)

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(shipment_id__icontains=q) | Q(amazon_order_id__icontains=q)
            )
        return qs.order_by("shipment_id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tab"] = (self.request.GET.get("tab") or "all").lower()
        ctx["search_q"] = (self.request.GET.get("q") or "").strip()
        return ctx
