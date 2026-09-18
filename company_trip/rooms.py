"""Ghép phòng / room_key."""

from __future__ import annotations

import random
import string

from django.db import transaction

from company_trip.constants import ROOM_2, ROOM_3, ROOM_ORGANIZER, STATUS_REGISTERED
from company_trip.models import TripRegistration


def generate_room_key(length: int = 10) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


@transaction.atomic
def assign_room_group(main_reg: TripRegistration, companion_regs: list[TripRegistration], room_key: str = '') -> str:
    key = (room_key or '').strip() or generate_room_key()
    regs = [main_reg] + list(companion_regs)
    for reg in regs:
        reg.room_key = key
        reg.save(update_fields=['room_key', 'updated_at'])
    return key


@transaction.atomic
def clear_room_key(reg: TripRegistration) -> int:
    key = (reg.room_key or '').strip()
    if not key:
        return 0
    return TripRegistration.objects.filter(room_key=key).update(room_key='')


def apply_companions_on_register(reg: TripRegistration) -> None:
    """Sau khi lưu đăng ký: gán room_key; chỉ sync key cho companion đã đăng ký sẵn."""
    if reg.room_type == ROOM_ORGANIZER:
        reg.room_key = ''
        reg.companion1 = None
        reg.companion2 = None
        reg.companion1_name = ''
        reg.companion2_name = ''
        reg.organized_committee = True
        reg.save(update_fields=[
            'room_key', 'companion1', 'companion2',
            'companion1_name', 'companion2_name', 'organized_committee', 'updated_at',
        ])
        return

    companions = []
    if reg.companion1_id:
        companions.append(reg.companion1)
        reg.companion1_name = reg.companion1.full_name or reg.companion1.user.username
    if reg.companion2_id and reg.room_type == ROOM_3:
        companions.append(reg.companion2)
        reg.companion2_name = reg.companion2.full_name or reg.companion2.user.username
    elif reg.room_type == ROOM_2:
        reg.companion2 = None
        reg.companion2_name = ''

    reg.organized_committee = False

    existing_keys = set()
    if reg.room_key:
        existing_keys.add(reg.room_key)
    companion_regs = []
    for c in companions:
        other = TripRegistration.objects.filter(profile=c, status=STATUS_REGISTERED).first()
        if other:
            companion_regs.append(other)
            if other.room_key:
                existing_keys.add(other.room_key)

    key = next(iter(existing_keys)) if len(existing_keys) == 1 else generate_room_key()
    reg.room_key = key
    reg.save(update_fields=[
        'room_key', 'companion1', 'companion2',
        'companion1_name', 'companion2_name', 'organized_committee', 'updated_at',
    ])

    for other in companion_regs:
        if other.pk == reg.pk:
            continue
        other.room_key = key
        other.save(update_fields=['room_key', 'updated_at'])
