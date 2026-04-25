from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.core.exceptions import ValidationError


User = get_user_model()


class CheckoutForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
        widget=forms.Select(choices=[(value, value) for value in range(1, 11)]),
    )
    destination_x = forms.IntegerField(initial=9)
    destination_y = forms.IntegerField(initial=8)
    link_ups_account = forms.BooleanField(
        required=False,
        initial=True,
        label="Link this package to my UPS account",
    )
    ups_account = forms.EmailField(
        required=False,
        max_length=128,
        label="UPS Account Email",
        widget=forms.EmailInput(attrs={"placeholder": "name@example.com"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and user is not None:
            email = (getattr(user, "email", "") or "").strip()
            if email:
                self.fields["ups_account"].initial = email

    def clean(self):
        data = super().clean()
        if not data.get("link_ups_account"):
            data["ups_account"] = ""
            return data
        if not (data.get("ups_account") or "").strip():
            self.add_error(
                "ups_account",
                "Enter a UPS account email or turn off UPS account linking.",
            )
        return data


class UserSignupForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    class Meta:
        model = User
        fields = ("email",)
        labels = {"email": "Email"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].widget.attrs.update(
            {
                "placeholder": "name@example.com",
                "autocomplete": "email",
            }
        )

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise ValidationError("Enter a valid email address.")
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("That email is already registered.")
        if User.objects.filter(username__iexact=email).exists():
            raise ValidationError("That email is already registered.")
        return email

    def clean(self):
        data = super().clean()
        password1 = data.get("password1")
        password2 = data.get("password2")
        if password1 is not None and password2 is not None and password1 != password2:
            raise ValidationError("The two password fields did not match.")
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"]
        user.username = email
        user.email = email
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
        return user


class AmazonAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Email"
        self.fields["username"].widget.attrs.update(
            {
                "placeholder": "name@example.com",
                "autocomplete": "username",
            }
        )
        self.fields["password"].label = "Password"
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password"})


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name")
        labels = {
            "first_name": "First name",
            "last_name": "Last name",
        }


class AmazonPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Current password"
        self.fields["new_password1"].label = "New password"
        self.fields["new_password2"].label = "Confirm new password"
