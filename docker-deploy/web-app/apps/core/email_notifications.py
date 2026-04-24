import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Package

logger = logging.getLogger(__name__)

INTEROP_USER = "_amazon_interop"


def notify_package_packed(package: Package) -> None:
    _send_package_email(
        package,
        subject=f"MiniUPS shipment {package.shipment_id} is packed",
        message=(
            f"Your shipment {package.shipment_id} has been packed and is ready for pickup.\n\n"
            f"Destination: ({package.dest_x}, {package.dest_y})"
        ),
    )


def notify_package_loaded(package: Package) -> None:
    truck_label = f"Truck #{package.truck_id}" if package.truck_id is not None else "The assigned truck"
    _send_package_email(
        package,
        subject=f"MiniUPS shipment {package.shipment_id} is loaded",
        message=(
            f"Your shipment {package.shipment_id} has been loaded onto {truck_label}.\n\n"
            f"Destination: ({package.dest_x}, {package.dest_y})"
        ),
    )


def notify_destination_updated(package: Package) -> None:
    _send_package_email(
        package,
        subject=f"MiniUPS shipment {package.shipment_id} destination updated",
        message=(
            f"The destination for your shipment {package.shipment_id} was updated.\n\n"
            f"New destination: ({package.dest_x}, {package.dest_y})"
        ),
    )


def notify_package_delivered(package: Package) -> None:
    _send_package_email(
        package,
        subject=f"MiniUPS shipment {package.shipment_id} delivered",
        message=(
            f"Your shipment {package.shipment_id} has arrived at its destination.\n\n"
            f"Delivered to: ({package.dest_x}, {package.dest_y})"
        ),
    )


def _send_package_email(package: Package, *, subject: str, message: str) -> bool:
    user = getattr(package, "user", None)
    recipient = (getattr(user, "email", "") or "").strip()
    if not recipient or getattr(user, "username", "") == INTEROP_USER:
        return False

    try:
        send_mail(
            subject,
            message,
            getattr(settings, "DEFAULT_FROM_EMAIL", None),
            [recipient],
            fail_silently=False,
        )
        return True
    except Exception as exc:
        logger.warning(
            "failed to send shipment email shipment=%s recipient=%s: %s",
            package.shipment_id,
            recipient,
            exc,
        )
        return False
