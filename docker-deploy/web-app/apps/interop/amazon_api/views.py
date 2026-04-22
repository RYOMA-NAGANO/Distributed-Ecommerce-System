from types import SimpleNamespace

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.services import (
    ShipmentNotFoundError,
    ShipmentStateError,
    mark_package_loaded_for_delivery,
)

from .serializers import AmazonPackageCreateSerializer, AmazonPackageResponseSerializer


def _get_shared_secret(request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :].strip()

    return request.headers.get("X-UPS-Interop-Secret", "").strip()


@method_decorator(csrf_exempt, name="dispatch")
class AmazonInteropAPIView(APIView):
    authentication_classes = []
    permission_classes = [IsAuthenticated]

    def perform_authentication(self, request):
        secret = _get_shared_secret(request)
        if not secret or secret != settings.INTEROP_SHARED_SECRET:
            raise AuthenticationFailed("Invalid interop secret.")

        # DRF expects `request.user` / `request.auth` to be set for IsAuthenticated.
        request.user = SimpleNamespace(is_authenticated=True)
        request.auth = secret


class PackageCreateView(AmazonInteropAPIView):
    def post(self, request):
        serializer = AmazonPackageCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        package = serializer.save()
        return Response(AmazonPackageResponseSerializer(package).data, status=status.HTTP_201_CREATED)


class PackageLoadedView(AmazonInteropAPIView):
    def post(self, request, shipment_id: str):
        try:
            package = mark_package_loaded_for_delivery(shipment_id, restrict_to_user=None)
        except ShipmentNotFoundError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ShipmentStateError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        return Response(AmazonPackageResponseSerializer(package).data, status=status.HTTP_200_OK)
