from django.urls import path

from .auip_views import (
    ShipmentCreateView,
    ShipmentDestinationView,
    ShipmentDetailView,
    ShipmentLoadedView,
    ShipmentPickupView,
    ShipmentReadyView,
)

urlpatterns = [
    path("shipments/", ShipmentCreateView.as_view(), name="auip-shipment-create"),
    path("shipments/<str:shipment_id>/pickup/", ShipmentPickupView.as_view(), name="auip-shipment-pickup"),
    path("shipments/<str:shipment_id>/ready/", ShipmentReadyView.as_view(), name="auip-shipment-ready"),
    path("shipments/<str:shipment_id>/loaded/", ShipmentLoadedView.as_view(), name="auip-shipment-loaded"),
    path(
        "shipments/<str:shipment_id>/destination/",
        ShipmentDestinationView.as_view(),
        name="auip-shipment-destination",
    ),
    path("shipments/<str:shipment_id>/", ShipmentDetailView.as_view(), name="auip-shipment-detail"),
]
