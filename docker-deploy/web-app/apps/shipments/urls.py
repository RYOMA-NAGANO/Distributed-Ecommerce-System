from django.urls import path

from .views import ShipmentListView


urlpatterns = [
    path("", ShipmentListView.as_view(), name="my-shipments"),
]
