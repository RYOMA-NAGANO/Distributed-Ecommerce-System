from django.urls import path

from .views import SignupView, UPSLoginView, UPSLogoutView, settings_view


urlpatterns = [
    path("login/", UPSLoginView.as_view(), name="login"),
    path("logout/", UPSLogoutView.as_view(), name="logout"),
    path("signup/", SignupView.as_view(), name="signup"),
    path("settings/", settings_view, name="account-settings"),
]
