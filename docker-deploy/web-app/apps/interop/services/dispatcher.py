from apps.interop.models import OutboundCommand


class CommandDispatcher:
    def queue(self, channel, seqnum, payload):
        return OutboundCommand.objects.create(
            channel=channel,
            seqnum=seqnum,
            payload=payload,
        )
