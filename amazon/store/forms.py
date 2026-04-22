from django import forms


class CheckoutForm(forms.Form):
    quantity = forms.IntegerField(
        min_value=1,
        max_value=10,
        initial=1,
        widget=forms.Select(choices=[(value, value) for value in range(1, 11)]),
    )
    destination_x = forms.IntegerField(initial=9)
    destination_y = forms.IntegerField(initial=8)
    ups_account = forms.CharField(
        max_length=64,
        required=False,
        strip=True,
    )
