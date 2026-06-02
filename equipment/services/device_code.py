"""Sinh và chuẩn hoá mã thiết bị."""

from __future__ import annotations

import re

CODE_PREFIX = 'TB'
AGENT_CODE_PREFIX = 'PC'
_CODE_PATTERN = re.compile(rf'^{CODE_PREFIX}-(\d+)$', re.IGNORECASE)
_AGENT_CODE_PATTERN = re.compile(rf'^{AGENT_CODE_PREFIX}-(\d+)$', re.IGNORECASE)


def normalize_device_code(value: str | None) -> str:
    return (value or '').strip().upper()


def allocate_device_code() -> str:
    from equipment.models import Device

    max_n = 0
    for code in Device.objects.filter(device_code__startswith=f'{CODE_PREFIX}-').values_list('device_code', flat=True):
        match = _CODE_PATTERN.match(code or '')
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f'{CODE_PREFIX}-{max_n + 1:06d}'


def allocate_agent_device_code() -> str:
    """Mã thiết bị từ agent — tiền tố PC- (khác TB- khi tạo tay)."""
    from equipment.models import Device

    max_n = 0
    prefix = f'{AGENT_CODE_PREFIX}-'
    for code in Device.objects.filter(device_code__startswith=prefix).values_list('device_code', flat=True):
        match = _AGENT_CODE_PATTERN.match(code or '')
        if match:
            max_n = max(max_n, int(match.group(1)))
    return f'{AGENT_CODE_PREFIX}-{max_n + 1:06d}'
