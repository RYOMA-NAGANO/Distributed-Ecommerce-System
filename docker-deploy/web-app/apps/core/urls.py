from django.urls import path

from .views import (
    PackageListView,
    home,
)


urlpatterns = [
    path("", home, name="home"),
    path("packages/", PackageListView.as_view(), name="my-packages"),
    path("shipments/", PackageListView.as_view(), name="my-shipments"),
]
