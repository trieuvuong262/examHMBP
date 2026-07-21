"""Đọc thiết lập chung SX (singleton DB)."""

from __future__ import annotations

from decimal import Decimal


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
