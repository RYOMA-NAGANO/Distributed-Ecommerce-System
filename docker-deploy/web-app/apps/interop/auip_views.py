from rest_framework import status
from rest_framework.response import Response

from apps.core.auip_services import (
    auip_confirm_loaded,
    auip_create_shipment,
    auip_get_shipment_dict,
    auip_mark_ready,
    auip_try_send_load_request_when_possible,
    auip_request_pickup,
    auip_update_destination,
)
from apps.core.models import Package
from apps.core.services import NoAvailableTruckError, ShipmentNotFoundError, ShipmentStateError
from apps.interop.idempotency import check_idempotency, save_idempotency
from apps.interop.services.world_binding import get_world_binding

from .auip_auth import InteropAPIView


def _err(code, message, shipment_id=None, http_status=400):
    body = {"error_code": code, "message": message}
    if shipment_id is not None:
        body["shipment_id"] = shipment_id
    return Response(body, status=http_status)


def _validate_item(it):
    return (
        isinstance(it, dict)
        and "product_id" in it
        and "description" in it
        and "quantity" in it
    )


class ShipmentCreateView(InteropAPIView):
    def post(self, request):
        replay = check_idempotency(request)
        if replay is not None:
            return replay

        data = request.data
        for key in ("shipment_id", "world_id", "amazon_order_id", "warehouse", "destination", "items"):
            if key not in data:
                return _err("INVALID_REQUEST", f"Missing field: {key}")

        wh = data["warehouse"]
        dest = data["destination"]
        for label, obj in (("warehouse", wh), ("destination", dest)):
            for k in ("x", "y"):
                if k not in obj:
                    return _err("INVALID_REQUEST", f"{label}.{k} required")
        if "id" not in wh:
            return _err("INVALID_REQUEST", "warehouse.id required")

        items = data["items"]
        if not isinstance(items, list) or not items:
            return _err("INVALID_REQUEST", "items must be a non-empty list")
        for it in items:
            if not _validate_item(it):
                return _err("INVALID_REQUEST", "Each item needs product_id, description, quantity")

        try:
            package = auip_create_shipment(data)
        except ValueError as exc:
            if str(exc) == "duplicate_shipment":
                existing = Package.objects.filter(
                    shipment_id=data["shipment_id"],
                    world_id=int(data["world_id"]),
                ).first()
                if existing:
                    body = {
                        "shipment_id": existing.shipment_id,
                        "status": "created",
                        "tracking_number": existing.shipment_id,
                        "world_id": int(existing.world_id),
                    }
                    save_idempotency(request, status.HTTP_201_CREATED, body)
                    return Response(body, status=status.HTTP_201_CREATED)
                return _err(
                    "DUPLICATE_SHIPMENT",
                    "shipment_id must be unique within this world.",
                    data.get("shipment_id"),
                    409,
                )
            if str(exc) == "duplicate_world_package_id":
                return _err(
                    "DUPLICATE_PACKAGE_ID",
                    "world packageid must be unique within this world.",
                    data.get("shipment_id"),
                    409,
                )
            return _err("INVALID_REQUEST", str(exc))
        except Exception as exc:
            return _err("INVALID_REQUEST", str(exc))

        body = {
            "shipment_id": package.shipment_id,
            "status": "created",
            "tracking_number": package.shipment_id,
            "world_id": int(package.world_id),
        }
        save_idempotency(request, status.HTTP_201_CREATED, body)
        return Response(body, status=status.HTTP_201_CREATED)


class ShipmentPickupView(InteropAPIView):
    def post(self, request, shipment_id):
        replay = check_idempotency(request)
        if replay is not None:
            return replay

        data = request.data
        for key in ("warehouse_id", "world_id"):
            if key not in data:
                return _err("INVALID_REQUEST", f"Missing field: {key}", shipment_id)

        try:
            package = auip_request_pickup(
                shipment_id,
                int(data["warehouse_id"]),
                int(data["world_id"]),
            )
        except ShipmentNotFoundError:
            return _err("NOT_FOUND", "Unknown shipment_id.", shipment_id, 404)
        except ShipmentStateError as exc:
            return _err("INVALID_STATE", str(exc), shipment_id, 409)
        except NoAvailableTruckError as exc:
            return _err("NO_TRUCK", str(exc), shipment_id, 503)

        body = {
            "shipment_id": package.shipment_id,
            "status": "truck_en_route",
            "world_id": int(package.world_id),
        }
        save_idempotency(request, status.HTTP_200_OK, body)
        return Response(body, status=status.HTTP_200_OK)


class ShipmentReadyView(InteropAPIView):
    def post(self, request, shipment_id):
        replay = check_idempotency(request)
        if replay is not None:
            return replay

        data = request.data
        for key in ("warehouse_id", "world_id"):
            if key not in data:
                return _err("INVALID_REQUEST", f"Missing field: {key}", shipment_id)

        try:
            package = auip_mark_ready(
                shipment_id,
                int(data["warehouse_id"]),
                int(data["world_id"]),
            )
        except ShipmentNotFoundError:
            return _err("NOT_FOUND", "Unknown shipment_id.", shipment_id, 404)
        except ShipmentStateError as exc:
            return _err("INVALID_STATE", str(exc), shipment_id, 409)

        auip_try_send_load_request_when_possible(shipment_id)

        body = {
            "shipment_id": package.shipment_id,
            "status": "packed",
            "world_id": int(package.world_id),
        }
        save_idempotency(request, status.HTTP_200_OK, body)
        return Response(body, status=status.HTTP_200_OK)


class ShipmentLoadedView(InteropAPIView):
    def post(self, request, shipment_id):
        replay = check_idempotency(request)
        if replay is not None:
            return replay

        data = request.data
        for key in ("truck_id", "warehouse_id", "world_id"):
            if key not in data:
                return _err("INVALID_REQUEST", f"Missing field: {key}", shipment_id)

        try:
            package = auip_confirm_loaded(
                shipment_id,
                int(data["truck_id"]),
                int(data["warehouse_id"]),
                int(data["world_id"]),
            )
        except ShipmentNotFoundError:
            return _err("NOT_FOUND", "Unknown shipment_id.", shipment_id, 404)
        except ShipmentStateError as exc:
            return _err("INVALID_STATE", str(exc), shipment_id, 409)

        body = {
            "shipment_id": package.shipment_id,
            "status": "loaded",
            "world_id": int(package.world_id),
        }
        save_idempotency(request, status.HTTP_200_OK, body)
        return Response(body, status=status.HTTP_200_OK)


class ShipmentDetailView(InteropAPIView):
    def get(self, request, shipment_id):
        try:
            body = auip_get_shipment_dict(shipment_id)
        except ShipmentNotFoundError:
            return _err("NOT_FOUND", "Unknown shipment_id.", shipment_id, 404)
        return Response(body, status=status.HTTP_200_OK)


class ShipmentDestinationView(InteropAPIView):
    def put(self, request, shipment_id):
        replay = check_idempotency(request)
        if replay is not None:
            return replay

        data = request.data
        for key in ("x", "y", "reason"):
            if key not in data:
                return _err("INVALID_REQUEST", f"Missing field: {key}", shipment_id)

        try:
            package = auip_update_destination(
                shipment_id,
                int(data["x"]),
                int(data["y"]),
                str(data["reason"]),
            )
        except ShipmentNotFoundError:
            return _err("NOT_FOUND", "Unknown shipment_id.", shipment_id, 404)
        except ShipmentStateError as exc:
            return _err("INVALID_STATE", str(exc), shipment_id, 409)

        body = {
            "shipment_id": package.shipment_id,
            "status": "updated",
            "destination": {"x": package.dest_x, "y": package.dest_y},
            "world_id": int(package.world_id),
        }
        save_idempotency(request, status.HTTP_200_OK, body)
        return Response(body, status=status.HTTP_200_OK)


class WorldBindingView(InteropAPIView):
    def get(self, request):
        binding = get_world_binding()
        if binding is None or binding.result != "connected!":
            return _err("WORLD_NOT_READY", "UPS has not established a World connection yet.", http_status=503)
        body = {
            "world_id": int(binding.world_id),
            "result": binding.result,
            "updated_at": binding.updated_at.isoformat(),
        }
        return Response(body, status=status.HTTP_200_OK)
