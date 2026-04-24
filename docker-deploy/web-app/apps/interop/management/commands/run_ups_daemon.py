import time
import socket
from importlib import import_module

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.core import auip_states as S
from apps.core.auip_services import (
    auip_recover_stale_pickup_requests,
    auip_recover_stuck_loading,
    auip_requeue_interrupted_deliveries_for_truck,
    auip_reconcile_truck_arrivals,
    auip_rotate_pickup_truck,
    auip_retry_pending_load_requests,
    auip_set_truck_arrived_for_truck,
    record_status_update,
)
from apps.core.email_notifications import notify_package_delivered
from apps.core.models import Package, PositionUpdate, Truck
from apps.interop.services import amazon_client
from apps.interop.services.world_response_dedupe import claim_world_response_seq
from apps.interop.services.seqnum import allocate_next_seqnum
from apps.interop.services.world_binding import clear_world_binding, get_world_binding, set_world_binding


class Command(BaseCommand):
    help = "Start the UPS daemon that talks to the World simulator and Amazon."
    _current_world_id: int | None = None
    _last_truck_query_at: dict[int, float]
    _PICKUP_DISPATCH_TRUCK_STATUSES = (
        Truck.TruckStatus.IDLE,
        Truck.TruckStatus.ARRIVE_WAREHOUSE,
        Truck.TruckStatus.DELIVERING,
    )
    _DELIVERY_DISPATCH_TRUCK_STATUSES = (
        Truck.TruckStatus.IDLE,
        Truck.TruckStatus.ARRIVE_WAREHOUSE,
        Truck.TruckStatus.DELIVERING,
    )
    _TRUCK_QUERY_PACKAGE_STATUSES = (
        S.TRUCK_EN_ROUTE,
        S.TRUCK_ARRIVED,
        S.PACKED,
        S.LOADING,
        S.LOADED,
        S.OUT_FOR_DELIVERY,
    )
    _PENDING_WAREHOUSE_LOAD_STATUSES = (
        S.TRUCK_ARRIVED,
        S.LOADING,
    )

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
        send_query = world_client.send_query
        self._last_truck_query_at = {}

        timeout = options["timeout"]
        read_timeout = options["read_timeout"]
        idle_log_seconds = options["idle_log_seconds"]
        session = None
        existing_binding = get_world_binding()
        if existing_binding is not None:
            try:
                session = open_world_session(
                    connect_timeout=timeout,
                    read_timeout=read_timeout,
                    world_id=int(existing_binding.world_id),
                )
            except WorldConnectionError:
                clear_world_binding()
                session = None

        if session is None:
            try:
                session = open_world_session(connect_timeout=timeout, read_timeout=read_timeout)
            except WorldConnectionError as exc:
                clear_world_binding()
                raise CommandError(str(exc)) from exc

        result = session.handshake
        self._current_world_id = int(result.world_id)
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
            auip_recover_stale_pickup_requests(world_id=self._current_world_id)
            auip_reconcile_truck_arrivals(world_id=self._current_world_id)
            auip_recover_stuck_loading(world_id=self._current_world_id)
            auip_retry_pending_load_requests(world_id=self._current_world_id)
            self._enqueue_truck_queries(session.sock, send_query)
            self._enqueue_pickups(session.sock, send_pickup)
            self._enqueue_deliveries(session.sock, send_deliver)

        def process_responses(responses):
            self.stdout.write(f"World response: {format_responses(responses)}")
            acks = collect_response_seqnums(responses)

            with transaction.atomic():
                for finished in responses.completions:
                    if claim_world_response_seq(self._current_world_id, int(finished.seqnum)):
                        self._handle_u_finished(finished)

                for delivered in responses.delivered:
                    if claim_world_response_seq(self._current_world_id, int(delivered.seqnum)):
                        self._handle_u_delivery_made(delivered)

                for truck in responses.truckstatus:
                    if claim_world_response_seq(self._current_world_id, int(truck.seqnum)):
                        self._handle_u_truck(truck)

                for err in responses.error:
                    if claim_world_response_seq(self._current_world_id, int(err.seqnum)):
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
            clear_world_binding()
            session.sock.close()

    def _enqueue_pickups(self, sock, send_pickup):
        if self._current_world_id is None:
            return
        candidates = (
            Package.objects.select_related("truck")
            .filter(
                world_id=int(self._current_world_id),
                status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
                pickup_seqnum__isnull=True,
            )
            .order_by("shipment_id")[:10]
        )

        for package in candidates:
            with transaction.atomic():
                locked = (
                    Package.objects.select_for_update()
                    .filter(
                        world_id=int(self._current_world_id),
                        shipment_id=package.shipment_id,
                        status__in=[S.TRUCK_EN_ROUTE, S.PACKED],
                        pickup_seqnum__isnull=True,
                    )
                    .first()
                )
                if locked is None:
                    continue

                dispatch_truck = self._select_dispatchable_pickup_truck()
                if dispatch_truck is None:
                    if locked.truck_id is not None:
                        locked.truck = None
                        locked.save(update_fields=["truck"])
                    continue

                seq = allocate_next_seqnum()
                send_pickup(
                    sock,
                    truck_id=dispatch_truck.truck_id,
                    warehouse_id=locked.warehouse_id,
                    seqnum=seq,
                    acks=None,
                )
                Truck.objects.filter(truck_id=dispatch_truck.truck_id).exclude(
                    truck_status=Truck.TruckStatus.INVALID
                ).update(truck_status=Truck.TruckStatus.TRAVELING)

                locked.truck = dispatch_truck
                locked.pickup_seqnum = seq
                locked.save(update_fields=["truck", "pickup_seqnum"])

    def _select_dispatchable_pickup_truck(self) -> Truck | None:
        if self._current_world_id is None:
            return None
        priority = {
            Truck.TruckStatus.IDLE: 0,
            Truck.TruckStatus.ARRIVE_WAREHOUSE: 1,
            Truck.TruckStatus.DELIVERING: 2,
        }
        trucks = list(
            Truck.objects.select_for_update()
            .filter(truck_status__in=self._PICKUP_DISPATCH_TRUCK_STATUSES)
            .order_by("truck_id")
        )
        trucks.sort(key=lambda t: (priority.get(t.truck_status, 99), int(t.truck_id)))

        for truck in trucks:
            if not self._truck_has_pending_warehouse_loads(int(truck.truck_id)):
                return truck
        return None

    def _enqueue_truck_queries(self, sock, send_query, interval_seconds: float = 1.0):
        if self._current_world_id is None:
            return

        now = time.monotonic()
        truck_ids = [
            int(truck_id)
            for truck_id in Package.objects.filter(
                world_id=int(self._current_world_id),
                truck_id__isnull=False,
                status__in=self._TRUCK_QUERY_PACKAGE_STATUSES,
            )
            .values_list("truck_id", flat=True)
            .distinct()
        ]
        active_ids = set(truck_ids)
        for truck_id in list(self._last_truck_query_at.keys()):
            if truck_id not in active_ids:
                del self._last_truck_query_at[truck_id]

        for truck_id in truck_ids:
            last_sent = self._last_truck_query_at.get(truck_id, 0.0)
            if now - last_sent < interval_seconds:
                continue
            seq = allocate_next_seqnum()
            send_query(sock, truck_id=truck_id, seqnum=seq, acks=None)
            self._last_truck_query_at[truck_id] = now

    def _enqueue_deliveries(self, sock, send_deliver):
        if self._current_world_id is None:
            return
        candidates = (
            Package.objects.select_related("truck")
            .filter(
                world_id=int(self._current_world_id),
                status__in=[S.LOADED, S.OUT_FOR_DELIVERY],
                delivery_seqnum__isnull=True,
                truck__isnull=False,
                truck__truck_status__in=self._DELIVERY_DISPATCH_TRUCK_STATUSES,
            )
            .order_by("shipment_id")[:10]
        )

        for package in candidates:
            with transaction.atomic():
                locked = (
                    Package.objects.select_for_update()
                    .filter(
                        world_id=int(self._current_world_id),
                        shipment_id=package.shipment_id,
                        status__in=[S.LOADED, S.OUT_FOR_DELIVERY],
                        delivery_seqnum__isnull=True,
                    )
                    .first()
                )
                if locked is None or locked.world_package_id is None:
                    continue
                if locked.truck_id is None:
                    continue
                if self._truck_has_pending_warehouse_loads(int(locked.truck_id)):
                    continue

                seq = allocate_next_seqnum()
                send_deliver(
                    sock,
                    truck_id=int(locked.truck_id),
                    world_package_id=int(locked.world_package_id),
                    dest_x=locked.dest_x,
                    dest_y=locked.dest_y,
                    seqnum=seq,
                    acks=None,
                )

                locked.delivery_seqnum = seq
                previous_status = locked.status
                locked.status = S.OUT_FOR_DELIVERY
                locked.save(update_fields=["delivery_seqnum", "status"])
                if locked.status != previous_status:
                    record_status_update(locked, locked.status)
                Truck.objects.filter(truck_id=int(locked.truck_id)).update(
                    truck_status=Truck.TruckStatus.DELIVERING
                )

            pkg = Package.objects.filter(shipment_id=locked.shipment_id).first()
            if pkg is not None:
                try:
                    amazon_client.notify_out_for_delivery(pkg)
                except Exception as exc:
                    self.stdout.write(self.style.WARNING(f"notify_out_for_delivery: {exc}"))

    def _handle_u_finished(self, finished):
        if self._current_world_id is None:
            return
        status = (finished.status or "").upper()
        truck_id = int(finished.truckid)
        seq = int(finished.seqnum)

        packages = Package.objects.select_related("truck").filter(
            world_id=int(self._current_world_id),
            truck_id=truck_id,
        )
        if not packages.exists():
            return

        self._record_truck_package_positions(
            truck_id=truck_id,
            x=int(finished.x),
            y=int(finished.y),
        )
        arrived_at_wh = ("WH" in status) or ("WAREHOUSE" in status)

        if arrived_at_wh:
            Truck.objects.filter(truck_id=truck_id).update(
                truck_status=Truck.TruckStatus.ARRIVE_WAREHOUSE
            )
            auip_requeue_interrupted_deliveries_for_truck(
                truck_id=truck_id,
                world_id=int(self._current_world_id),
            )
            auip_set_truck_arrived_for_truck(
                truck_id, int(finished.x), int(finished.y), pickup_seqnum=seq
            )
        else:
            # Non-warehouse completion means delivery queue finished.
            Truck.objects.filter(truck_id=truck_id).update(truck_status=Truck.TruckStatus.IDLE)

    def _handle_u_delivery_made(self, delivered):
        if self._current_world_id is None:
            return
        world_package_id = int(delivered.packageid)
        truck_id = int(delivered.truckid)

        package = (
            Package.objects.select_related("truck")
            .filter(
                world_id=int(self._current_world_id),
                world_package_id=world_package_id,
                truck_id=truck_id,
            )
            .first()
        )
        if package is None:
            return

        if package.status == S.OUT_FOR_DELIVERY:
            previous_status = package.status
            package.status = S.DELIVERED
            package.delivery_seqnum = None
            package.save(update_fields=["status", "delivery_seqnum"])
            if package.status != previous_status:
                record_status_update(package, package.status)
                transaction.on_commit(
                    lambda shipment_id=package.shipment_id: self._notify_delivered_email(shipment_id)
                )
            try:
                amazon_client.notify_delivered(package, package.dest_x, package.dest_y)
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"notify_delivered: {exc}"))

    def _notify_delivered_email(self, shipment_id: str) -> None:
        package = Package.objects.select_related("user", "truck").filter(shipment_id=shipment_id).first()
        if package is not None:
            notify_package_delivered(package)

    def _handle_u_truck(self, truck_msg):
        if self._current_world_id is None:
            return
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
        for package in Package.objects.filter(
            world_id=int(self._current_world_id),
            truck_id=truck_id,
        ).exclude(status=S.DELIVERED).only("shipment_id"):
            self._record_package_position_if_changed(package.shipment_id, x, y, now_epoch)

    def _record_truck_package_positions(self, truck_id: int, x: int, y: int):
        if self._current_world_id is None:
            return
        now_epoch = int(time.time())
        shipment_ids = list(
            Package.objects.filter(
                world_id=int(self._current_world_id),
                truck_id=int(truck_id),
            )
            .exclude(status=S.DELIVERED)
            .values_list("shipment_id", flat=True)
        )
        for shipment_id in shipment_ids:
            self._record_package_position_if_changed(shipment_id, x, y, now_epoch)

    def _record_package_position_if_changed(self, shipment_id: str, x: int, y: int, update_time: int) -> bool:
        latest = (
            PositionUpdate.objects.filter(shipment_id=shipment_id)
            .order_by("-update_time", "-id")
            .values("x", "y")
            .first()
        )
        if latest is not None and int(latest["x"]) == int(x) and int(latest["y"]) == int(y):
            return False
        PositionUpdate.objects.create(
            shipment_id=shipment_id,
            x=int(x),
            y=int(y),
            update_time=int(update_time),
        )
        return True

    def _truck_has_pending_warehouse_loads(self, truck_id: int) -> bool:
        if self._current_world_id is None:
            return False
        return Package.objects.filter(
            world_id=int(self._current_world_id),
            truck_id=int(truck_id),
            status__in=self._PENDING_WAREHOUSE_LOAD_STATUSES,
        ).exists()

    def _handle_u_err(self, err_msg):
        if self._current_world_id is None:
            return
        origin_seq = int(err_msg.originseqnum)
        detail = err_msg.err or "unknown world error"

        pickup_pkg = (
            Package.objects.select_related("truck")
            .filter(world_id=int(self._current_world_id), pickup_seqnum=origin_seq)
            .first()
        )
        if pickup_pkg is not None:
            lowered = detail.lower()
            if pickup_pkg.truck_id is not None and "cannot find truck" in lowered:
                Truck.objects.filter(truck_id=pickup_pkg.truck_id).update(
                    truck_status=Truck.TruckStatus.INVALID
                )
            old_truck_id, new_truck_id = auip_rotate_pickup_truck(pickup_pkg.shipment_id)
            self.stdout.write(
                self.style.WARNING(
                    f"World pickup error shipment={pickup_pkg.shipment_id} "
                    f"origin_seq={origin_seq}: {detail}; "
                    f"reassigned truck {old_truck_id} -> {new_truck_id}, will retry pickup."
                )
            )
            return

        delivery_pkg = (
            Package.objects.select_related("truck")
            .filter(world_id=int(self._current_world_id), delivery_seqnum=origin_seq)
            .first()
        )
        if delivery_pkg is not None:
            previous_status = delivery_pkg.status
            delivery_pkg.delivery_seqnum = None
            delivery_pkg.status = S.LOADED
            delivery_pkg.save(update_fields=["delivery_seqnum", "status"])
            if delivery_pkg.status != previous_status:
                record_status_update(delivery_pkg, delivery_pkg.status)
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
        if "ARRIVE" in upper or "WAREHOUSE" in upper:
            return Truck.TruckStatus.ARRIVE_WAREHOUSE
        if "TRAVEL" in upper:
            return Truck.TruckStatus.TRAVELING
        if "LOAD" in upper:
            return Truck.TruckStatus.LOADING
        if "DELIVER" in upper:
            return Truck.TruckStatus.DELIVERING
        return None
