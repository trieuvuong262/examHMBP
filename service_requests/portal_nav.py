"""Số lượng chờ xử lý — hiển thị trên sidebar (không dùng tab trong trang)."""

from service_requests.flow import FLOW_DE_XUAT, FLOW_HO_TRO
from service_requests.models import RequestType
from service_requests.permissions import can_manage_recurring_catalog, pending_steps_for_user


def pending_count_for_flow(user, flow_tab: str) -> int:
    if not user.is_authenticated:
        return 0
    qs = pending_steps_for_user(user)
    if flow_tab == FLOW_HO_TRO:
        return qs.filter(request__request_type__code=RequestType.CODE_IT_REPAIR).count()
    return qs.filter(request__request_type__code=RequestType.CODE_ASSET_PURCHASE).count()


def portal_nav_context(user) -> dict:
    if not user.is_authenticated:
        return {
            'jp_de_xuat_pending_count': 0,
            'jp_ho_tro_pending_count': 0,
            'jp_can_manage_catalog': False,
        }
    return {
        'jp_de_xuat_pending_count': pending_count_for_flow(user, FLOW_DE_XUAT),
        'jp_ho_tro_pending_count': pending_count_for_flow(user, FLOW_HO_TRO),
        'jp_can_manage_catalog': can_manage_recurring_catalog(user),
    }
