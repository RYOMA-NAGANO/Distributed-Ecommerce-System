from django.core.management.base import BaseCommand, CommandError

from apps.core.services import NoAvailableTruckError, create_package_with_assigned_truck


class Command(BaseCommand):
    help = "Create a package row and assign the first idle truck."

    def add_arguments(self, parser):
        parser.add_argument("shipment_id")
        parser.add_argument("username")
        parser.add_argument("dest_x", type=int)
        parser.add_argument("dest_y", type=int)
        parser.add_argument("--email", default="")
        parser.add_argument("--warehouse-id", type=int, default=0)
        parser.add_argument("--world-package-id", type=int, default=None)

    def handle(self, *args, **options):
        try:
            package = create_package_with_assigned_truck(
                shipment_id=options["shipment_id"],
                username=options["username"],
                dest_x=options["dest_x"],
                dest_y=options["dest_y"],
                email=options["email"],
                warehouse_id=options["warehouse_id"],
                world_package_id=options["world_package_id"],
            )
        except (ValueError, NoAvailableTruckError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Created package {package.shipment_id}"))
        self.stdout.write(f"user={package.user.username}")
        self.stdout.write(f"truck_id={package.truck_id}")
        self.stdout.write(f"status={package.status}")
        self.stdout.write(f"destination=({package.dest_x}, {package.dest_y})")
        self.stdout.write(f"warehouse_id={package.warehouse_id}")
        self.stdout.write(f"world_package_id={package.world_package_id}")
