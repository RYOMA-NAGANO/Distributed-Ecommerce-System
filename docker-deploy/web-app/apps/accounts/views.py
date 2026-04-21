from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.views.generic.edit import CreateView

from .forms import UPSAuthenticationForm, UserSignupForm


class UPSLoginView(LoginView):
    authentication_form = UPSAuthenticationForm
    template_name = "accounts/login.html"


class UPSLogoutView(LogoutView):
    next_page = reverse_lazy("home")


class SignupView(CreateView):
    form_class = UserSignupForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("login")
