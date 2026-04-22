import hashlib

from rest_framework.response import Response

from apps.interop.models import IdempotencyRecord


def check_idempotency(request):
    """
    For mutating AUIP requests: require Idempotency-Key; replay prior response or 409 on body mismatch.
    Returns a Response to return immediately, or None to proceed.
    """
    if request.method not in ("POST", "PUT"):
        return None
    key = (request.headers.get("Idempotency-Key") or "").strip()
    if not key:
        return Response(
            {
                "error_code": "MISSING_IDEMPOTENCY_KEY",
                "message": "Idempotency-Key header is required for this request.",
            },
            status=400,
        )
    method = request.method.upper()
    path = request.get_full_path()[:512]
    body_hash = hashlib.sha256(request.body or b"").hexdigest()
    row = IdempotencyRecord.objects.filter(key=key[:64], method=method, path=path).first()
    if row:
        if row.body_hash != body_hash:
            return Response(
                {
                    "error_code": "IDEMPOTENCY_CONFLICT",
                    "message": "Idempotency-Key reused with a different request body.",
                },
                status=409,
            )
        return Response(row.response_body, status=row.response_status)
    return None


def save_idempotency(request, status: int, body: dict):
    key = (request.headers.get("Idempotency-Key") or "").strip()
    method = request.method.upper()
    path = request.get_full_path()[:512]
    body_hash = hashlib.sha256(request.body or b"").hexdigest()
    IdempotencyRecord.objects.create(
        key=key[:64],
        method=method,
        path=path,
        body_hash=body_hash,
        response_status=status,
        response_body=body,
    )
