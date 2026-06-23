"""Sinh và chuẩn hoá mã thiết bị."""

from __future__ import annotations

import re

CODE_PREFIX = 'TB'
PC_CODE_PREFIX = 'PC'
_CODE_PATTERN = re.compile(rf'^{CODE_PREFIX}-(\d+)$', re.IGNORECASE)
_PC_CODE_PATTERN = re.compile(rf'^{PC_CODE_PREFIX}-(\d+)$', re.IGNORECASE)


def normalize_device_code(value: str | None) -> str:
    return (value or '').strip().upper()


def _allocate_code_for_prefix(prefix: str, *, width: int = 6) -> str:
    from equipment.models import Device

    prefix = (prefix or CODE_PREFIX).strip().upper()
    pattern = re.compile(rf'^{re.escape(prefix)}-(\d+)$', re.IGNORECASE)
    max_n = 0
    for code in Device.objects.filter(device_code__istartswith=f'{prefix}-').values_list('device_code', flat=True):
        match = pattern.match(code or '')
        if match:
            max_n = max(max_n, int(match.group(1)))

    for step in range(1, 100_000):
        candidate = f'{prefix}-{max_n + step:0{width}d}'
        if not Device.objects.filter(device_code__iexact=candidate).exists():
            return candidate
    raise RuntimeError(f'Không còn mã thiết bị trống cho prefix {prefix}')


def allocate_device_code() -> str:
    return _allocate_code_for_prefix(CODE_PREFIX)


def allocate_pc_device_code() -> str:
    """Mã PC-000001… cho thiết bị IT đăng ký qua script quét."""
    return _allocate_code_for_prefix(PC_CODE_PREFIX)
