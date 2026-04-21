from apps.interop.models import OutboundCommand


class SeqNumAllocator:
    def next_for_channel(self, channel):
        latest = OutboundCommand.objects.filter(channel=channel).order_by("-seqnum").first()
        return 1 if latest is None else latest.seqnum + 1
