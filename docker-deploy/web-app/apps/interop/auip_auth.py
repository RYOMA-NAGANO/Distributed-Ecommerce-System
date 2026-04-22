from types import SimpleNamespace

from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView


def _get_shared_secret(request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[len("Bearer ") :].strip()
    return request.headers.get("X-UPS-Interop-Secret", "").strip()


@method_decorator(csrf_exempt, name="dispatch")
class InteropAPIView(APIView):
    authentication_classes = []
    permission_classes = [IsAuthenticated]

    def perform_authentication(self, request):
        secret = _get_shared_secret(request)
        if not secret or secret != settings.INTEROP_SHARED_SECRET:
            raise AuthenticationFailed("Invalid interop secret.")
        request.user = SimpleNamespace(is_authenticated=True)
        request.auth = secret
