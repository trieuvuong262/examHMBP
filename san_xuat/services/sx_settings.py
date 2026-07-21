"""Đọc thiết lập chung SX (singleton DB)."""

from __future__ import annotations

import re
from decimal import Decimal

_PREFIX_DEFAULTS = {
    'mo': 'LSX',
    'ycx': 'YCX',
    'stat': 'TKSX',
    'fg': 'YCNTP',
    'qc_req': 'YCKT',
    'qc_sheet': 'PKT',
    'qc_alert': 'CBQC',
    'wip_ho': 'BG',
    'wip_ret': 'TRABTP',
    'disassembly': 'LTD',
    'npl_surplus': 'NPLT',
    'packing': 'DG',
    'subcontract': 'GC',
    'work_assign': 'GV',
    'plan_overall': 'KHTT',
    'plan_npl': 'KHNVL',
    'plan_detail': 'KHCT',
    'npl_pr': 'YCM',
    'po': 'DMH',
    'cost_std': 'GTDM',
    'cost_order': 'GTDH',
    'actual_cost': 'GTT',
    'ncr': 'NCR',
    'downtime': 'DT',
}


def load_sx_settings():
    from san_xuat.hub_models import SxGeneralSettings

    return SxGeneralSettings.load()


def sx_gate(field: str, default: str = "block") -> str:
    cfg = load_sx_settings()
    val = (getattr(cfg, field, None) or default or "block")
    val = str(val).strip().lower()
    return val if val in {"off", "warn", "block"} else default


def sx_bool(field: str, default: bool = True) -> bool:
    cfg = load_sx_settings()
    return bool(getattr(cfg, field, default))


def sx_int(field: str, default: int = 0, *, min_v: int = 0, max_v: int = 10_000) -> int:
    cfg = load_sx_settings()
    try:
        n = int(getattr(cfg, field, default) or default)
    except (TypeError, ValueError):
        n = default
    return max(min_v, min(max_v, n))


def sx_decimal(field: str, default: str | Decimal = "0") -> Decimal:
    cfg = load_sx_settings()
    raw = getattr(cfg, field, None)
    try:
        return Decimal(str(raw if raw is not None else default))
    except Exception:
        return Decimal(str(default))


def sx_prefix(kind: str, fallback: str | None = None) -> str:
    """Prefix mã chứng từ theo thiết lập (vd. kind='mo' → LSX)."""
    default = (fallback or _PREFIX_DEFAULTS.get(kind) or kind.upper()).strip().upper() or 'DOC'
    field = f'prefix_{kind}'
    cfg = load_sx_settings()
    raw = getattr(cfg, field, None)
    val = str(raw or '').strip().upper() or default
    val = re.sub(r'[^A-Z0-9\-]', '', val) or default
    return val[:16]
