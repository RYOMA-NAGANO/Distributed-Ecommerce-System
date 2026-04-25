from django.urls import path

from .auip_views import (
    ShipmentCreateView,
    ShipmentDestinationView,
    ShipmentDetailView,
    ShipmentLoadFailedView,
    ShipmentLoadedView,
    ShipmentPickupView,
    ShipmentReadyView,
    WorldBindingView,
)

urlpatterns = [
    path("world", WorldBindingView.as_view(), name="auip-world-binding-noslash"),
    path("world/", WorldBindingView.as_view(), name="auip-world-binding"),
    path("shipments", ShipmentCreateView.as_view(), name="auip-shipment-create-noslash"),
    path("shipments/", ShipmentCreateView.as_view(), name="auip-shipment-create"),
    path("shipments/<str:shipment_id>/pickup", ShipmentPickupView.as_view(), name="auip-shipment-pickup-noslash"),
    path("shipments/<str:shipment_id>/pickup/", ShipmentPickupView.as_view(), name="auip-shipment-pickup"),
    path("shipments/<str:shipment_id>/ready", ShipmentReadyView.as_view(), name="auip-shipment-ready-noslash"),
    path("shipments/<str:shipment_id>/ready/", ShipmentReadyView.as_view(), name="auip-shipment-ready"),
    path("shipments/<str:shipment_id>/loaded", ShipmentLoadedView.as_view(), name="auip-shipment-loaded-noslash"),
    path("shipments/<str:shipment_id>/loaded/", ShipmentLoadedView.as_view(), name="auip-shipment-loaded"),
    path("shipments/<str:shipment_id>/load-failed", ShipmentLoadFailedView.as_view(), name="auip-shipment-load-failed-noslash"),
    path("shipments/<str:shipment_id>/load-failed/", ShipmentLoadFailedView.as_view(), name="auip-shipment-load-failed"),
    path(
        "shipments/<str:shipment_id>/destination",
        ShipmentDestinationView.as_view(),
        name="auip-shipment-destination-noslash",
    ),
    path(
        "shipments/<str:shipment_id>/destination/",
        ShipmentDestinationView.as_view(),
        name="auip-shipment-destination",
    ),
    path("shipments/<str:shipment_id>", ShipmentDetailView.as_view(), name="auip-shipment-detail-noslash"),
    path("shipments/<str:shipment_id>/", ShipmentDetailView.as_view(), name="auip-shipment-detail"),
]
