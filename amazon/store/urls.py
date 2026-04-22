from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("products/", views.product_list, name="product_list"),
    path("products/<str:product_id>/", views.product_detail, name="product_detail"),
    path("orders/<str:amazon_order_id>/", views.order_detail, name="order_detail"),
    path("tracking/", views.tracking_lookup, name="tracking_lookup"),
    path("healthz/", views.healthz, name="healthz"),
    path("api/truck-arrived", views.truck_arrived, name="truck_arrived"),
    path("api/load-request", views.load_request, name="load_request"),
    path("api/out-for-delivery", views.out_for_delivery, name="out_for_delivery"),
    path("api/delivered", views.delivered, name="delivered"),
]
