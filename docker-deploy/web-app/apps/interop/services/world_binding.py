from django.db import transaction

from apps.interop.models import WorldBinding

_SINGLETON_ID = 1


@transaction.atomic
def set_world_binding(world_id: int, result: str = "") -> WorldBinding:
    binding, _ = WorldBinding.objects.select_for_update().update_or_create(
        id=_SINGLETON_ID,
        defaults={
            "world_id": int(world_id),
            "result": (result or "")[:64],
        },
    )
    return binding


def get_world_binding() -> WorldBinding | None:
    return WorldBinding.objects.filter(id=_SINGLETON_ID).first()
