from django.db import models


class OutboundSeq(models.Model):
    """
    Single-row counter for World command seqnums (global across pickups/deliveries/etc.).
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    next_seq = models.BigIntegerField(default=1)

    class Meta:
        db_table = "interop_outbound_seq"

    def __str__(self):
        return f"OutboundSeq(next_seq={self.next_seq})"


class IdempotencyRecord(models.Model):
    """Stores replay for POST/PUT with Idempotency-Key (method + path + key)."""

    key = models.CharField(max_length=64)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=512)
    body_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "interop_idempotency"
        constraints = [
            models.UniqueConstraint(fields=["key", "method", "path"], name="interop_idem_key_method_path"),
        ]


class WorldBinding(models.Model):
    """
    Singleton row with the active World simulator id chosen by UPS.
    Amazon can read this through the interop API to join the same world.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1)
    world_id = models.BigIntegerField()
    result = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "interop_world_binding"
