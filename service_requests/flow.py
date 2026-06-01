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


def flow_my_url_name(flow_tab):
    if flow_tab == FLOW_HO_TRO:
        return 'service_requests:ho_tro_my'
    return 'service_requests:de_xuat_my'


def flow_pending_url_name(flow_tab):
    if flow_tab == FLOW_HO_TRO:
        return 'service_requests:ho_tro_pending'
    return 'service_requests:de_xuat_pending'


def flow_create_url_name(flow_tab):
    if flow_tab == FLOW_HO_TRO:
        return 'service_requests:create_it_repair'
    return 'service_requests:create'
