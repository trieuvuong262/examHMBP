"""Phân quyền module theo luồng Yêu cầu."""

from hrm.menu_permissions import user_can_access_menu
from hrm.module_permissions import MODULE_DE_XUAT, MODULE_HO_TRO, user_can_access_module

from .flow import FLOW_DE_XUAT, FLOW_HO_TRO, normalize_flow_tab
from .models import RequestType

FLOW_MODULE = {
    FLOW_DE_XUAT: MODULE_DE_XUAT,
    FLOW_HO_TRO: MODULE_HO_TRO,
}


def module_for_flow(flow_tab) -> str:
    return FLOW_MODULE[normalize_flow_tab(flow_tab)]


def module_for_request(service_request) -> str:
    if getattr(service_request, 'is_it_repair', False):
        return MODULE_HO_TRO
    if service_request.request_type_id:
        code = service_request.request_type.code
        if code == RequestType.CODE_IT_REPAIR:
            return MODULE_HO_TRO
    return MODULE_DE_XUAT


def flow_list_menu_key(list_kind: str) -> str:
    return {
        'my': 'my',
        'pending': 'pending',
        'involved': 'pending',
    }.get(list_kind, 'my')


def user_can_access_flow_list(user, flow_tab, *, list_kind: str = 'my') -> bool:
    module = module_for_flow(flow_tab)
    return user_can_access_menu(user, module, flow_list_menu_key(list_kind))


def user_can_access_flow(user, flow_tab) -> bool:
    return user_can_access_flow_list(user, flow_tab, list_kind='my')


def user_can_access_any_request_module(user) -> bool:
    return (
        user_can_access_module(user, MODULE_DE_XUAT)
        or user_can_access_module(user, MODULE_HO_TRO)
    )
