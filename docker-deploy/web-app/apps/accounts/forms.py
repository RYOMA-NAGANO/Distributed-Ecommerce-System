from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import UPSUser


class UPSUserCreationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = UPSUser
        fields = ("username", "email", "amazon_account_name")


class UPSAuthenticationForm(AuthenticationForm):
    pass
