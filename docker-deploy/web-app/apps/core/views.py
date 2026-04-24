import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views import View
from django.views.generic import ListView

from . import auip_states as S
from .auip_services import update_destination_for_owner
from .forms import DestinationUpdateForm
from .models import Package, TrackedShipment
from .services import ShipmentNotFoundError, ShipmentStateError

INTEROP_OWNER = "_amazon_interop"
PRODUCT_NAME_OVERRIDES = {
    1001: "Compact Shipping Box Set",
}


def _status_label(status: str) -> str:
    normalized = str(status).strip().lower()
    labels = {
        S.TRUCK_EN_ROUTE: "Truck on the way",
    }
    if normalized in labels:
        return labels[normalized]
    return normalized.replace("_", " ").title()


def _build_map_bounds(points: list[tuple[int, int]]) -> dict[str, int]:
    if not points:
        return {"min_x": -20, "max_x": 20, "min_y": -20, "max_y": 20}

    min_x = min(point[0] for point in points)
    max_x = max(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_y = max(point[1] for point in points)

    span_x = max(max_x - min_x, 40)
    span_y = max(max_y - min_y, 40)
    center_x = (min_x + max_x) // 2
    center_y = (min_y + max_y) // 2

    return {
        "min_x": int(center_x - span_x // 2 - 2),
        "max_x": int(center_x + span_x // 2 + 2),
        "min_y": int(center_y - span_y // 2 - 2),
        "max_y": int(center_y + span_y // 2 + 2),
    }


def _infer_current_position(package, position_events):
    if package.status == S.DELIVERED:
        return int(package.dest_x), int(package.dest_y), "Delivered destination"
    if position_events:
        latest = max(position_events, key=lambda update: (int(update.update_time), int(update.id)))
        return int(latest.x), int(latest.y), "Reported from truck updates"
    return int(package.warehouse_x), int(package.warehouse_y), "Estimated at warehouse"


def home(request):
    return render(request, "core/home.html")


def claim_search_results_for_user(search_qs, user):
    """
    Amazon-created shipments start owned by the interop placeholder user.
    The first real user who searches a matching package atomically claims it.
    """
    interop_owner_id = (
        get_user_model()
        .objects.filter(username=INTEROP_OWNER)
        .values_list("id", flat=True)
        .first()
    )
    if interop_owner_id is None:
        return

    matched_shipment_ids = list(search_qs.values_list("shipment_id", flat=True))
    if not matched_shipment_ids:
        return

    with transaction.atomic():
        # Lock the candidate rows so ownership is decided once (first claimant wins).
        claimable_ids = list(
            Package.objects.select_for_update()
            .filter(
                shipment_id__in=matched_shipment_ids,
                user_id=interop_owner_id,
            )
            .values_list("shipment_id", flat=True)
        )
        if claimable_ids:
            Package.objects.filter(
                shipment_id__in=claimable_ids,
                user_id=interop_owner_id,
            ).update(user_id=user.id)

        owned_ids = list(
            Package.objects.filter(
                shipment_id__in=matched_shipment_ids,
                user_id=user.id,
            ).values_list("shipment_id", flat=True)
        )
        for shipment_id in owned_ids:
            TrackedShipment.objects.update_or_create(
                user=user,
                package_id=shipment_id,
            )


class PackageListView(LoginRequiredMixin, ListView):
    model = Package
    template_name = "core/packages.html"
    context_object_name = "packages"

    def get_queryset(self):
        q = (self.request.GET.get("q") or "").strip()
        base_qs = Package.objects.select_related("truck", "user").prefetch_related(
            "position_updates",
            "destination_updates",
            "status_updates",
        )
        tab = (self.request.GET.get("tab") or "all").lower()

        if q:
            match_filter = Q(shipment_id__icontains=q) | Q(amazon_order_id__icontains=q)
            try:
                numeric_q = int(q)
            except (TypeError, ValueError):
                numeric_q = None

            if numeric_q is not None:
                match_filter |= Q(world_package_id=numeric_q)
                match_filter |= Q(items__contains=[{"product_id": numeric_q}])

            matched_qs = base_qs.filter(match_filter)
            claim_search_results_for_user(matched_qs, self.request.user)
            qs = matched_qs.filter(user=self.request.user)
        else:
            qs = base_qs.filter(user=self.request.user)

        if tab == "active":
            qs = qs.exclude(status__in=[S.DELIVERED, S.CANCELED, S.DELIVERY_FAILED])
        elif tab == "delivered":
            qs = qs.filter(status=S.DELIVERED)

        return qs.order_by("shipment_id")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        packages = list(ctx["packages"])
        self._attach_detail_timelines(packages)
        ctx["packages"] = packages
        ctx["tab"] = (self.request.GET.get("tab") or "all").lower()
        ctx["search_q"] = (self.request.GET.get("q") or "").strip()
        ctx["show_destination_modal"] = any(
            package.user_id == self.request.user.id and package.status != S.DELIVERED
            for package in packages
        )
        return ctx

    def _attach_detail_timelines(self, packages):
        for package in packages:
            events = []
            position_events = list(package.position_updates.all())
            destination_events = list(package.destination_updates.all())
            status_events = list(package.status_updates.all())
            package.status_label = _status_label(package.status)

            for update in status_events:
                events.append(
                    {
                        "time": int(update.update_time),
                        "type": "Status",
                        "description": f"Status updated to {_status_label(update.status)}",
                        "status": str(update.status),
                    }
                )

            if not status_events:
                events.append(
                    {
                        "time": 0,
                        "type": "Status",
                        "description": f"Current status: {_status_label(package.status)}",
                        "status": str(package.status),
                    }
                )

            for update in destination_events:
                events.append(
                    {
                        "time": int(update.update_time),
                        "type": "Destination",
                        "description": f"Destination updated to ({update.x}, {update.y})",
                        "x": int(update.x),
                        "y": int(update.y),
                    }
                )

            for update in position_events:
                events.append(
                    {
                        "time": int(update.update_time),
                        "type": "Position",
                        "description": f"Position updated to ({update.x}, {update.y})",
                        "x": int(update.x),
                        "y": int(update.y),
                    }
                )
            events.sort(key=lambda item: (item["time"], item["type"], item["description"]))
            package.detail_events_json = json.dumps(events)

            item_payloads = package.items if isinstance(package.items, list) else []
            package.item_summaries = []
            for item in item_payloads:
                if not isinstance(item, dict):
                    continue
                quantity = item.get("quantity") or 1
                product_id = item.get("product_id")
                display_name = str(item.get("name") or "").strip()
                if not display_name:
                    try:
                        pid = int(product_id)
                    except (TypeError, ValueError):
                        pid = None
                    if pid is not None and pid in PRODUCT_NAME_OVERRIDES:
                        display_name = PRODUCT_NAME_OVERRIDES[pid]
                if not display_name:
                    display_name = str(item.get("description") or f"Product {product_id or ''}").strip()
                package.item_summaries.append(f"{display_name} x{quantity}")
            if not package.item_summaries:
                package.item_summaries = ["Item payload unavailable"]

            current_x, current_y, current_note = _infer_current_position(package, position_events)
            package.current_position_x = current_x
            package.current_position_y = current_y
            package.current_position_note = current_note
            package.current_position_display = f"({current_x}, {current_y})"

            map_points = [
                (int(package.warehouse_x), int(package.warehouse_y)),
                (int(package.dest_x), int(package.dest_y)),
                (int(current_x), int(current_y)),
            ]
            map_points.extend((int(update.x), int(update.y)) for update in position_events)
            map_points.extend((int(update.x), int(update.y)) for update in destination_events)
            bounds = _build_map_bounds(map_points)
            package.map_min_x = bounds["min_x"]
            package.map_max_x = bounds["max_x"]
            package.map_min_y = bounds["min_y"]
            package.map_max_y = bounds["max_y"]


class PackageDestinationUpdateView(LoginRequiredMixin, View):
    def post(self, request, shipment_id):
        form = DestinationUpdateForm(request.POST)
        next_url = request.POST.get("next") or "my-packages"
        if not form.is_valid():
            messages.error(request, "Enter a valid destination.")
            return redirect(next_url)

        try:
            update_destination_for_owner(
                shipment_id=shipment_id,
                user=request.user,
                x=form.cleaned_data["dest_x"],
                y=form.cleaned_data["dest_y"],
            )
        except ShipmentNotFoundError:
            messages.error(request, "Shipment not found.")
            return redirect(next_url)
        except ShipmentStateError as exc:
            if "Only the package owner" in str(exc):
                return HttpResponseForbidden(str(exc))
            messages.error(request, str(exc))
            return redirect(next_url)

        messages.success(request, "Destination updated.")
        return redirect(next_url)
