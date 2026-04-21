from django.db import models


class OutboundCommand(models.Model):
    CHANNEL_WORLD = "world"
    CHANNEL_AMAZON = "amazon"

    channel = models.CharField(max_length=16)
    seqnum = models.BigIntegerField(unique=True)
    payload = models.JSONField(default=dict, blank=True)
    acked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["seqnum"]

    def __str__(self):
        return f"{self.channel}:{self.seqnum}"
