import logging
import json
import hashlib

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.http import JsonResponse
from django.http import Http404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic.edit import CreateView
from django.views.decorators.csrf import csrf_exempt

from .forms import (
    AmazonAuthenticationForm,
    AmazonPasswordChangeForm,
    CheckoutForm,
    UserProfileForm,
    UserSignupForm,
)
from .models import HttpDirection, HttpIdempotencyRecord, Order, Shipment, ShipmentStatus
from .services.callback_service import (
    CallbackBadRequest,
    CallbackConflict,
    handle_delivered,
    handle_load_request,
    handle_out_for_delivery,
    handle_truck_arrived,
)
from .services.catalog import get_catalog_metadata, get_catalog_product, get_catalog_products
from .services.order_service import create_order_from_product
from .services.status import build_timeline_steps

logger = logging.getLogger(__name__)


RESOLVED_TRANSIENT_EVENT_STATUSES = {
    "load_failed": {
        ShipmentStatus.LOADED,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
    },
    "truck_arrived_failed": {
        ShipmentStatus.TRUCK_ARRIVED,
        ShipmentStatus.LOADING,
        ShipmentStatus.LOADED,
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
    },
    "delivery_failed": {
        ShipmentStatus.DELIVERED,
    },
}


class AmazonLoginView(LoginView):
    authentication_form = AmazonAuthenticationForm
    template_name = "store/login.html"
    redirect_authenticated_user = True


class AmazonLogoutView(LogoutView):
    next_page = reverse_lazy("home")


class SignupView(CreateView):
    form_class = UserSignupForm
    template_name = "store/signup.html"

    def form_valid(self, form):
        self.object = form.save()
        auth_login(self.request, self.object)
        messages.success(self.request, "Account created.")
        redirect_to = self.request.POST.get("next") or self.request.GET.get("next")
        if redirect_to:
            return redirect(redirect_to)
        return redirect(reverse_lazy("home"))


@login_required
def account_settings(request):
    profile_form = UserProfileForm(instance=request.user, prefix="profile")
    password_form = AmazonPasswordChangeForm(request.user, prefix="password")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "profile":
            profile_form = UserProfileForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Profile updated.")
                return redirect("account_settings")
        elif action == "password":
            password_form = AmazonPasswordChangeForm(request.user, request.POST, prefix="password")
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Password updated.")
                return redirect("account_settings")

    return render(
        request,
        "store/settings.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )


def _callback_secret(request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :].strip()
    return request.headers.get("X-Amazon-Interop-Secret", "").strip()


def home(request):
    catalog_products = get_catalog_products()
    context = {
        "featured_products": catalog_products[:4],
    }
    return render(request, "store/home.html", context)


def product_list(request):
    search_query = request.GET.get("q", "").strip()
    filtered_products = get_catalog_products()

    if search_query:
        lowered_query = search_query.lower()
        filtered_products = [
            product
            for product in filtered_products
            if lowered_query in product["name"].lower()
        ]

    paginator = Paginator(filtered_products, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "products": page_obj.object_list,
        "page_obj": page_obj,
        "search_query": search_query,
        "total_products": paginator.count,
    }
    return render(request, "store/product_list.html", context)


def product_detail(request, product_id):
    product = get_catalog_product(product_id)
    if product is None:
        raise Http404("Product not found")

    if request.method == "POST":
        if not request.user.is_authenticated:
            return redirect(f"{reverse_lazy('login')}?next={request.path}")
        form = CheckoutForm(request.POST)
        if form.is_valid():
            try:
                order, _shipment = create_order_from_product(
                    user=request.user,
                    product_data=product,
                    quantity=form.cleaned_data["quantity"],
                    destination_x=form.cleaned_data["destination_x"],
                    destination_y=form.cleaned_data["destination_y"],
                )
                return redirect("order_detail", amazon_order_id=order.amazon_order_id)
            except Exception as exc:
                logger.exception("Failed to create order for product %s", product_id)
                form.add_error(None, f"Could not create order: {exc}")
    else:
        form = CheckoutForm()

    context = {
        "product": product,
        "form": form,
    }
    return render(request, "store/product_detail.html", context)


@login_required
def order_detail(request, amazon_order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related("shipments__items__product"),
        amazon_order_id=amazon_order_id,
        user=request.user,
    )
    detail_context = _build_order_detail_context(
        order,
        event_page_number=request.GET.get("events_page"),
    )

    if detail_context is None:
        return JsonResponse({"detail": "Shipment not found for order"}, status=404)
    return render(request, "store/order_detail.html", detail_context)


@login_required
def tracking_lookup(request):
    query = request.GET.get("query", "").strip()
    lookup_error = ""

    if query:
        order = Order.objects.filter(
            amazon_order_id=query,
            user=request.user,
        ).first()
        if order:
            return redirect("order_detail", amazon_order_id=order.amazon_order_id)

        shipment = (
            Shipment.objects.select_related("order")
            .filter(
                Q(shipment_id=query) | Q(tracking_number=query),
                order__user=request.user,
            )
            .order_by("-created_at")
            .first()
        )
        if shipment and shipment.order:
            return redirect("order_detail", amazon_order_id=shipment.order.amazon_order_id)

        lookup_error = f'No order or shipment matched "{query}".'

    recent_shipments = (
        Shipment.objects.select_related("order", "warehouse")
        .filter(order__user=request.user)
        .order_by("-created_at")
    )
    recent_shipments_page_obj = Paginator(recent_shipments, 5).get_page(
        request.GET.get("shipments_page")
    )
    context = {
        "query": query,
        "lookup_error": lookup_error,
        "recent_shipments": recent_shipments_page_obj.object_list,
        "recent_shipments_page_obj": recent_shipments_page_obj,
    }
    return render(request, "store/tracking_lookup.html", context)


def healthz(request):
    """Simple health endpoint for local smoke checks."""
    return JsonResponse({"status": "ok"})


@csrf_exempt
def truck_arrived(request):
    return _handle_callback_request(request, handle_truck_arrived)


@csrf_exempt
def load_request(request):
    return _handle_callback_request(request, handle_load_request)


@csrf_exempt
def out_for_delivery(request):
    return _handle_callback_request(request, handle_out_for_delivery)


@csrf_exempt
def delivered(request):
    return _handle_callback_request(request, handle_delivered)


def _handle_callback_request(request, handler):
    if request.method != "POST":
        return JsonResponse({"detail": "Method not allowed"}, status=405)

    expected_secret = (getattr(settings, "AMAZON_INTEROP_SECRET", "") or "").strip()
    if expected_secret and _callback_secret(request) != expected_secret:
        return JsonResponse({"detail": "Invalid interop secret"}, status=403)

    idempotency_key = request.headers.get("Idempotency-Key")
    if not idempotency_key:
        return JsonResponse({"detail": "Idempotency-Key header is required"}, status=400)

    body_bytes = request.body or b"{}"
    body_hash = hashlib.sha256(body_bytes).hexdigest()

    try:
        payload = json.loads(body_bytes.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"detail": "Invalid JSON body"}, status=400)

    with transaction.atomic():
        record = (
            HttpIdempotencyRecord.objects.select_for_update()
            .filter(
                direction=HttpDirection.INBOUND,
                method=request.method,
                path=request.path,
                idempotency_key=idempotency_key,
            )
            .first()
        )

        if record:
            if record.body_hash != body_hash:
                return JsonResponse(
                    {"detail": "Idempotency-Key reused with different request body"},
                    status=409,
                )
            if record.response_status is not None:
                return JsonResponse(record.response_body or {}, status=record.response_status)
        else:
            record = HttpIdempotencyRecord.objects.create(
                direction=HttpDirection.INBOUND,
                peer="ups",
                method=request.method,
                path=request.path,
                idempotency_key=idempotency_key,
                body_hash=body_hash,
            )

        shipment = None
        try:
            result = handler(payload)
            response_status = 200
            response_body = {
                "shipment_id": result.shipment_id,
                "status": result.status,
                "world_id": result.world_id,
            }
            shipment = Shipment.objects.filter(
                shipment_id=result.shipment_id,
                world_id=result.world_id,
            ).first()
        except CallbackBadRequest as exc:
            response_status = 400
            response_body = {"detail": str(exc)}
        except CallbackConflict as exc:
            response_status = 409
            response_body = {"detail": str(exc)}
        except Exception as exc:
            logger.exception("Callback handler failed")
            response_status = 500
            response_body = {"detail": str(exc)}

        record.shipment = shipment
        record.response_status = response_status
        record.response_body = response_body
        record.processed_at = timezone.now()
        record.save(
            update_fields=[
                "shipment",
                "response_status",
                "response_body",
                "processed_at",
                "updated_at",
            ]
        )

    return JsonResponse(response_body, status=response_status)


def _build_order_detail_context(order: Order, event_page_number=None):
    shipment_model = order.shipments.select_related("warehouse").order_by("-created_at").first()
    if shipment_model is None:
        return None

    shipment_items = []
    for item in shipment_model.items.select_related("product"):
        shipment_items.append(
            {
                "product_id": item.product.product_id,
                "name": item.product.name or item.description_snapshot,
                "quantity": item.quantity,
                "price": item.product.price,
            }
        )

    shipment = {
        "shipment_id": shipment_model.shipment_id,
        "tracking_number": shipment_model.tracking_number or shipment_model.shipment_id,
        "status": shipment_model.status,
        "world_id": shipment_model.world_id,
        "warehouse_label": (
            f"Warehouse {shipment_model.warehouse.warehouse_id} "
            f"({shipment_model.warehouse.x}, {shipment_model.warehouse.y})"
        ),
        "destination": f"({shipment_model.destination_x}, {shipment_model.destination_y})",
    }

    shipment_events = _dedupe_shipment_events(
        _filter_resolved_transient_events(
            shipment_model.events.order_by("-created_at", "-id"),
            shipment_model.status,
        )
    )
    shipment_events_page_obj = Paginator(shipment_events, 8).get_page(event_page_number)

    return {
        "order": order,
        "shipment": shipment,
        "shipment_items": shipment_items,
        "timeline_steps": build_timeline_steps(shipment_model.status),
        "shipment_events": shipment_events_page_obj.object_list,
        "shipment_events_page_obj": shipment_events_page_obj,
    }


def _dedupe_shipment_events(events):
    deduped_events = []
    last_signature = None

    for event in events:
        signature = (
            event.source,
            event.event_type,
            event.status_snapshot,
            event.error_message,
        )
        if signature == last_signature:
            continue
        deduped_events.append(event)
        last_signature = signature

    return deduped_events


def _filter_resolved_transient_events(events, current_status):
    filtered_events = []

    for event in events:
        resolved_statuses = RESOLVED_TRANSIENT_EVENT_STATUSES.get(event.event_type)
        if resolved_statuses and current_status in resolved_statuses:
            continue
        filtered_events.append(event)

    return filtered_events
