"""Hằng số luồng module Yêu cầu — Đề xuất mới & Hỗ trợ kỹ thuật."""

FLOW_DE_XUAT = 'de_xuat'
FLOW_HO_TRO = 'ho_tro'

FLOW_LABELS = {
    FLOW_DE_XUAT: 'Đề xuất mới',
    FLOW_HO_TRO: 'Hỗ trợ kỹ thuật',
}

_LEGACY_FLOW_MAP = {
    'procurement': FLOW_DE_XUAT,
    'it_repair': FLOW_HO_TRO,
}


def normalize_flow_tab(value=None, *, default=FLOW_DE_XUAT):
    if value in (FLOW_DE_XUAT, FLOW_HO_TRO):
        return value
    return _LEGACY_FLOW_MAP.get(value, default)
