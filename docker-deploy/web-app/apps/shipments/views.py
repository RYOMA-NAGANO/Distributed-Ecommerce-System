from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView

from .models import Shipment


class ShipmentListView(LoginRequiredMixin, ListView):
    model = Shipment
    template_name = "shipments/list.html"
    context_object_name = "shipments"

    def get_queryset(self):
        return Shipment.objects.filter(owner=self.request.user)
