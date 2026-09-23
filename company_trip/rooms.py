"""Ghép phòng / room_key."""

from __future__ import annotations

import random
import string

from django.db import transaction

from company_trip.constants import ROOM_COLLEAGUE, ROOM_ORGANIZER, ROOM_RELATIVE
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


_ROOM_SYNC_FIELDS = [
    'room_key', 'companion1', 'companion2',
    'companion1_name', 'companion2_name',
    'companion_confirmed', 'companion_confirmed_at', 'companion_email',
    'relative_full_name', 'relative_cccd', 'relative_phone',
    'relative_gender', 'relative_date_of_birth',
    'organized_committee', 'updated_at',
]


def _clear_relative(reg: TripRegistration) -> None:
    reg.relative_full_name = ''
    reg.relative_cccd = ''
    reg.relative_phone = ''
    reg.relative_gender = ''
    reg.relative_date_of_birth = None
    if reg.pk:
        reg.relatives.all().delete()


def _clear_colleague(reg: TripRegistration) -> None:
    reg.companion1 = None
    reg.companion2 = None
    reg.companion1_name = ''
    reg.companion2_name = ''
    reg.companion_confirmed = False
    reg.companion_confirmed_at = None
    reg.companion_email = ''


def apply_companions_on_register(reg: TripRegistration) -> None:
    """Chuẩn hóa người đi cùng và mã phòng theo loại đăng ký."""
    if reg.room_type == ROOM_ORGANIZER:
        reg.room_key = ''
        _clear_colleague(reg)
        _clear_relative(reg)
        reg.organized_committee = True
        reg.save(update_fields=_ROOM_SYNC_FIELDS)
        return

    if reg.room_type == ROOM_RELATIVE:
        _clear_colleague(reg)
        reg.organized_committee = False
        if not (reg.room_key or '').strip():
            reg.room_key = generate_room_key()
        reg.save(update_fields=_ROOM_SYNC_FIELDS)
        return

    if reg.room_type == ROOM_COLLEAGUE:
        _clear_relative(reg)
        reg.companion2 = None
        reg.companion2_name = ''
        if reg.companion1_id:
            reg.companion1_name = reg.companion1.full_name or reg.companion1.user.username
        else:
            reg.companion1_name = ''
        reg.organized_committee = False
        if not (reg.room_key or '').strip():
            reg.room_key = generate_room_key()
        reg.save(update_fields=_ROOM_SYNC_FIELDS)
