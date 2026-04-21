from django.core.management.base import BaseCommand

from apps.interop.services.world_client import build_connect_message


class Command(BaseCommand):
    help = "Start the UPS daemon that talks to the World simulator and Amazon."

    def handle(self, *args, **options):
        connect = build_connect_message()
        self.stdout.write(
            self.style.WARNING(
                "UPS daemon scaffold only. World connect message prepared for "
                f"{len(connect.trucks)} trucks."
            )
        )
