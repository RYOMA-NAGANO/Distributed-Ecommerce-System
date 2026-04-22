from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.shortcuts import redirect, render
from django.views.generic.edit import CreateView

from .forms import (
    UPSAuthenticationForm,
    UPSPasswordChangeForm,
    UserProfileForm,
    UserSignupForm,
)


class UPSLoginView(LoginView):
    authentication_form = UPSAuthenticationForm
    template_name = "accounts/login.html"


class UPSLogoutView(LogoutView):
    next_page = reverse_lazy("home")


class SignupView(CreateView):
    form_class = UserSignupForm
    template_name = "accounts/signup.html"
    success_url = reverse_lazy("login")

    def form_valid(self, form):
        messages.success(self.request, "Account created. Log in with your email and password.")
        return super().form_valid(form)


@login_required
def settings_view(request):
    profile_form = UserProfileForm(instance=request.user, prefix="profile")
    password_form = UPSPasswordChangeForm(request.user, prefix="password")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile":
            profile_form = UserProfileForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("account-settings")
        elif action == "password":
            password_form = UPSPasswordChangeForm(request.user, request.POST, prefix="password")
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated.")
                return redirect("account-settings")

    return render(
        request,
        "accounts/settings.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )
