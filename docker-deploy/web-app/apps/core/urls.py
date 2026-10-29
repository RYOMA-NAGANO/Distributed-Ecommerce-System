from django.urls import path

from .views import (
    PackageDestinationUpdateView,
    PackageHistoryView,
    PackageListView,
    home,
)


urlpatterns = [
    path("", home, name="home"),
    path("packages/", PackageListView.as_view(), name="my-packages"),
    path(
        "packages/<str:shipment_id>/destination/",
        PackageDestinationUpdateView.as_view(),
        name="package-destination-update",
    ),
    path(
        "packages/<str:shipment_id>/history/",
        PackageHistoryView.as_view(),
        name="package-history",
    ),
    path("shipments/", PackageListView.as_view(), name="my-shipments"),
]
