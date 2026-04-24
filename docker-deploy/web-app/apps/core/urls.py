from django.urls import path

from .views import (
    PackageDestinationUpdateView,
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
    path("shipments/", PackageListView.as_view(), name="my-shipments"),
]
