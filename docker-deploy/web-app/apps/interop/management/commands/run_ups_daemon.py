from django.core.management.base import BaseCommand, CommandError

from apps.interop.services.world_client import WorldConnectionError, connect_and_handshake


class Command(BaseCommand):
    help = "Start the UPS daemon that talks to the World simulator and Amazon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=float,
            default=10.0,
            help="Socket timeout in seconds for the initial World handshake.",
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]
        try:
            result = connect_and_handshake(timeout=timeout)
        except WorldConnectionError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Connected to World server at {result.host}:{result.port} "
                f"with {result.truck_count} trucks."
            )
        )
        self.stdout.write(f"worldid={result.world_id}")
        self.stdout.write(f"result={result.result}")
