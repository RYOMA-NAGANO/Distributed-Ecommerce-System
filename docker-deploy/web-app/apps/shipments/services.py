from .models import Shipment


def create_placeholder_shipment(tracking_number, destination_x, destination_y, owner=None):
    return Shipment.objects.create(
        tracking_number=tracking_number,
        destination_x=destination_x,
        destination_y=destination_y,
        owner=owner,
    )
