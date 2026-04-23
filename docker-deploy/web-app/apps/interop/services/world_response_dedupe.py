from django.db import IntegrityError

from apps.interop.models import WorldResponseSeq


def claim_world_response_seq(world_id: int, seqnum: int) -> bool:
    """
    Return True iff this world response seqnum is first-seen.
    """
    try:
        _, created = WorldResponseSeq.objects.get_or_create(
            world_id=int(world_id),
            seqnum=int(seqnum),
        )
        return bool(created)
    except IntegrityError:
        return False
