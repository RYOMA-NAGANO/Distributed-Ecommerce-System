from django.urls import path

from .views import PackageCreateView, PackageLoadedView


urlpatterns = [
    path("packages/", PackageCreateView.as_view(), name="amazon-package-create"),
    path("packages/<str:shipment_id>/loaded/", PackageLoadedView.as_view(), name="amazon-package-loaded"),
]
