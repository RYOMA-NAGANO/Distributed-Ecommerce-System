from django.contrib import admin

from .models import OutboundCommand


@admin.register(OutboundCommand)
class OutboundCommandAdmin(admin.ModelAdmin):
    list_display = ("channel", "seqnum", "acked", "created_at")
    list_filter = ("channel", "acked")
    search_fields = ("seqnum",)
