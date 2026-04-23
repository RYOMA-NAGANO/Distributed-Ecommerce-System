from django import forms


class DevCreatePackageForm(forms.Form):
    owner_username = forms.CharField(
        max_length=150,
        initial="dev_browser",
        help_text="Owner UPS username (no password; user is get_or_created).",
    )
    shipment_id = forms.CharField(max_length=100)
    dest_x = forms.IntegerField()
    dest_y = forms.IntegerField()
    warehouse_id = forms.IntegerField(initial=0, required=False)
    world_package_id = forms.IntegerField(
        required=False,
        help_text="Optional. If omitted and shipment_id is all digits, shipment_id is used as World package id.",
    )


class DevLoadedForm(forms.Form):
    shipment_id = forms.CharField(max_length=100)


class PackageSelfServiceForm(forms.Form):
    """Logged-in user creates a shipment (same backend as dev tools, tied to current user)."""

    shipment_id = forms.CharField(max_length=100, label="Shipment id")
    dest_x = forms.IntegerField(label="Destination X")
    dest_y = forms.IntegerField(label="Destination Y")
    warehouse_id = forms.IntegerField(initial=0, required=False, label="Warehouse id")
    world_package_id = forms.IntegerField(required=False, label="World package id (optional)")


class DestinationUpdateForm(forms.Form):
    dest_x = forms.IntegerField(label="Destination X")
    dest_y = forms.IntegerField(label="Destination Y")
