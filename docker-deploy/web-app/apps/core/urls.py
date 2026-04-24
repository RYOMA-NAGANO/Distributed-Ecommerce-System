from django.urls import path

from .views import (
    PackageDestinationUpdateView,
    PackageLivePositionView,
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
        "packages/<str:shipment_id>/live-position/",
        PackageLivePositionView.as_view(),
        name="package-live-position",
    ),
    path("shipments/", PackageListView.as_view(), name="my-shipments"),
]
