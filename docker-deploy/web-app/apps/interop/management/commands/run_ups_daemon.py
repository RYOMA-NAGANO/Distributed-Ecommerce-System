import time
import socket
from importlib import import_module

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core import auip_states as S
from apps.core.auip_services import (
    auip_reconcile_truck_arrivals,
    auip_retry_pending_load_requests,
    auip_set_truck_arrived_for_truck,
)
from apps.core.models import Package, PositionUpdate, Truck
from apps.interop.services import amazon_client
from apps.interop.services.seqnum import allocate_next_seqnum
from apps.interop.services.world_binding import set_world_binding


class Command(BaseCommand):
    help = "Start the UPS daemon that talks to the World simulator and Amazon."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=float,
            default=10.0,
            help="Socket timeout in seconds for the initial World handshake.",
        )
        parser.add_argument(
            "--idle-log-seconds",
            type=float,
            default=30.0,
            help="How often to log that the daemon is still waiting for World responses.",
        )
        parser.add_argument(
            "--read-timeout",
            type=float,
            default=2.0,
            help="Socket read timeout in seconds after the handshake (short timeouts let the daemon poll DB).",
        )

    def handle(self, *args, **options):
        world_client = import_module("apps.interop.services.world_client")
        WorldConnectionError = world_client.WorldConnectionError
        open_world_session = world_client.open_world_session
        receive_responses = world_client.receive_responses
        format_responses = world_client.format_responses
        collect_response_seqnums = world_client.collect_response_seqnums
        send_pickup = world_client.send_pickup
        send_deliver = world_client.send_deliver
        send_acks_only = world_client.send_acks_only

        timeout = options["timeout"]
        read_timeout = options["read_timeout"]
        idle_log_seconds = options["idle_log_seconds"]
        try:
            session = open_world_session(connect_timeout=timeout, read_timeout=read_timeout)
        except WorldConnectionError as exc:
            raise CommandError(str(exc)) from exc

        result = session.handshake
        self.stdout.write(
            self.style.SUCCESS(
                f"Connected to World server at {result.host}:{result.port} "
                f"with {result.truck_count} trucks."
            )
        )
        self.stdout.write(f"worldid={result.world_id}")
        self.stdout.write(f"result={result.result}")
        set_world_binding(result.world_id, result.result)

        last_idle_log = 0.0

        def on_idle():
            nonlocal last_idle_log
            now = time.monotonic()
            if now - last_idle_log >= idle_log_seconds:
                self.stdout.write("Waiting for World responses...")
                last_idle_log = now

        def maybe_enqueue_outbound():
            self._enqueue_pickups(session.sock, send_pickup)
            auip_reconcile_truck_arrivals()
            auip_retry_pending_load_requests()
            self._enqueue_deliveries(session.sock, send_deliver)

        def process_responses(responses):
            self.stdout.write(f"World response: {format_responses(responses)}")
            acks = collect_response_seqnums(responses)

            with transaction.atomic():
                for finished in responses.completions:
                    self._handle_u_finished(finished)

                for delivered in responses.delivered:
                    self._handle_u_delivery_made(delivered)

                for truck in responses.truckstatus:
                    self._handle_u_truck(truck)

                for err in responses.error:
                    self._handle_u_err(err)

            if acks:
                send_acks_only(session.sock, acks)

        try:
            while True:
                try:
                    maybe_enqueue_outbound()
                    responses = receive_responses(session.sock)
                except socket.timeout:
                    maybe_enqueue_outbound()
                    on_idle()
                    continue
                except WorldConnectionError as exc:
                    raise CommandError(str(exc)) from exc

                process_responses(responses)
        finally:
            session.sock.close()

    def _enqueue_pickups(self, sock, send_pickup):
        candidates = (
            Package.objects.select_related("truck")
            .filter(status=S.TRUCK_EN_ROUTE, pickup_seqnum__isnull=True, truck__isnull=False)
            .order_by("shipment_id")[:10]
        )

        for package in candidates:
            with transaction.atomic():
                locked = (
                    Package.objects.select_for_update()
                    .filter(
                        shipment_id=package.shipment_id,
                        status=S.TRUCK_EN_ROUTE,
                        pickup_seqnum__isnull=True,
                    )
                    .first()
                )
                if locked is None:
                    continue

                seq = allocate_next_seqnum()
                send_pickup(
                    sock,
                    truck_id=locked.truck_id,
                    warehouse_id=locked.warehouse_id,
                    seqnum=seq,
                    acks=None,
                )

                locked.pickup_seqnum = seq
                locked.save(update_fields=["pickup_seqnum"])

    def _enqueue_deliveries(self, sock, send_deliver):
        candidates = (
            Package.objects.select_related("truck")
            .filter(
                status=S.LOADED,
                delivery_seqnum__isnull=True,
                truck__isnull=False,
            )
            .order_by("shipment_id")[:10]
        )

        for package in candidates:
            with transaction.atomic():
                locked = (
                    Package.objects.select_for_update()
                    .filter(
                        shipment_id=package.shipment_id,
                        status=S.LOADED,
                        delivery_seqnum__isnull=True,
                    )
                    .first()
                )
                if locked is None or locked.world_package_id is None:
                    continue

                seq = allocate_next_seqnum()
                send_deliver(
                    sock,
                    truck_id=locked.truck_id,
                    world_package_id=int(locked.world_package_id),
                    dest_x=locked.dest_x,
                    dest_y=locked.dest_y,
                    seqnum=seq,
                    acks=None,
                )

                locked.delivery_seqnum = seq
                locked.status = S.OUT_FOR_DELIVERY
                locked.save(update_fields=["delivery_seqnum", "status"])

            pkg = Package.objects.filter(shipment_id=locked.shipment_id).first()
            if pkg is not None:
                try:
                    amazon_client.notify_out_for_delivery(pkg)
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(f"notify_out_for_delivery: {exc}"))

    def _handle_u_finished(self, finished):
        status = (finished.status or "").upper()
        truck_id = int(finished.truckid)
        seq = int(finished.seqnum)

        packages = Package.objects.select_related("truck").filter(truck_id=truck_id)
        if not packages.exists():
            return

        arrived_at_wh = ("WH" in status) or ("WAREHOUSE" in status)

        if arrived_at_wh:
            Truck.objects.filter(truck_id=truck_id).update(truck_status=Truck.TruckStatus.LOADING)
            auip_set_truck_arrived_for_truck(
                truck_id, int(finished.x), int(finished.y), pickup_seqnum=seq
            )
        else:
            Truck.objects.filter(truck_id=truck_id).update(truck_status=Truck.TruckStatus.TRAVELING)

    def _handle_u_delivery_made(self, delivered):
        world_package_id = int(delivered.packageid)
        truck_id = int(delivered.truckid)

        package = (
            Package.objects.select_related("truck")
            .filter(world_package_id=world_package_id, truck_id=truck_id)
            .first()
        )
        if package is None:
            return

        if package.status == S.OUT_FOR_DELIVERY:
            package.status = S.DELIVERED
            package.save(update_fields=["status"])
            try:
                amazon_client.notify_delivered(package, package.dest_x, package.dest_y)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"notify_delivered: {exc}"))

        Truck.objects.filter(truck_id=truck_id).update(truck_status=Truck.TruckStatus.IDLE)

    def _handle_u_truck(self, truck_msg):
        truck_id = int(truck_msg.truckid)
        x = int(truck_msg.x)
        y = int(truck_msg.y)
        status = truck_msg.status or ""

        truck_updates = {}
        mapped = self._map_world_truck_status(status)
        if mapped is not None:
            truck_updates["truck_status"] = mapped

        if truck_updates:
            Truck.objects.filter(truck_id=truck_id).update(**truck_updates)

        now_epoch = int(time.time())
        for package in Package.objects.filter(truck_id=truck_id).only("shipment_id"):
            PositionUpdate.objects.create(shipment_id=package.shipment_id, x=x, y=y, update_time=now_epoch)

    def _handle_u_err(self, err_msg):
        origin_seq = int(err_msg.originseqnum)
        detail = err_msg.err or "unknown world error"

        pickup_pkg = (
            Package.objects.select_related("truck")
            .filter(pickup_seqnum=origin_seq)
            .first()
        )
        if pickup_pkg is not None:
            pickup_pkg.pickup_seqnum = None
            pickup_pkg.status = S.TRUCK_EN_ROUTE
            pickup_pkg.save(update_fields=["pickup_seqnum", "status"])
            if pickup_pkg.truck_id is not None:
                Truck.objects.filter(truck_id=pickup_pkg.truck_id).update(
                    truck_status=Truck.TruckStatus.IDLE
                )
            self.stdout.write(
                self.style.WARNING(
                    f"World pickup error shipment={pickup_pkg.shipment_id} "
                    f"origin_seq={origin_seq}: {detail}; will retry pickup."
                )
            )
            return

        delivery_pkg = (
            Package.objects.select_related("truck")
            .filter(delivery_seqnum=origin_seq)
            .first()
        )
        if delivery_pkg is not None:
            delivery_pkg.delivery_seqnum = None
            delivery_pkg.status = S.LOADED
            delivery_pkg.save(update_fields=["delivery_seqnum", "status"])
            if delivery_pkg.truck_id is not None:
                Truck.objects.filter(truck_id=delivery_pkg.truck_id).update(
                    truck_status=Truck.TruckStatus.LOADING
                )
            self.stdout.write(
                self.style.WARNING(
                    f"World delivery error shipment={delivery_pkg.shipment_id} "
                    f"origin_seq={origin_seq}: {detail}; will retry delivery."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"World error origin_seq={origin_seq}: {detail} (no matching package seqnum)"
            )
        )

    def _map_world_truck_status(self, status: str):
        upper = (status or "").upper()
        if "IDLE" in upper:
            return Truck.TruckStatus.IDLE
        if "TRAVEL" in upper:
            return Truck.TruckStatus.TRAVELING
        if "LOAD" in upper:
            return Truck.TruckStatus.LOADING
        if "DELIVER" in upper:
            return Truck.TruckStatus.DELIVERING
        return None
