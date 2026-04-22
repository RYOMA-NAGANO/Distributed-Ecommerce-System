from django.db import transaction

from apps.interop.models import OutboundSeq


@transaction.atomic
def allocate_next_seqnum() -> int:
    row = OutboundSeq.objects.select_for_update().get(pk=1)
    seq = int(row.next_seq)
    row.next_seq = seq + 1
    row.save(update_fields=["next_seq"])
    return seq
