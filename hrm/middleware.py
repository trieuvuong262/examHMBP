from django.utils.module_loading import import_string

from hrm.menu_permissions import (
    handle_menu_access_denied,
    resolve_menu_from_request,
    user_can_access_resolved_menu,
)
from hrm.module_permissions import (
    MODULE_THIET_KE_SP,
    handle_department_access_denied,
    user_can_access_module,
)

# Module cho phép người ngoài quyền menu vào một số URL theo dữ liệu (vd. thành viên hồ sơ).
MEMBER_ACCESS_HOOKS = {
    MODULE_THIET_KE_SP: 'thiet_ke_sp.permissions.member_path_allowed',
}


def _member_access(user, module_key: str, path: str) -> bool:
    hook = MEMBER_ACCESS_HOOKS.get(module_key)
    return bool(hook) and import_string(hook)(user, path)


class DepartmentModuleAccessMiddleware:
    """Chặn URL module/menu không thuộc quyền phòng ban + nhóm quyền của user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            module_key, menu_key = resolve_menu_from_request(
                request.path,
                request.GET.get('tab'),
            )
            module_denied = module_key and not user_can_access_module(user, module_key)
            menu_denied = (
                not module_denied and module_key and menu_key
                and not user_can_access_resolved_menu(user, module_key, menu_key)
            )
            if (module_denied or menu_denied) and _member_access(user, module_key, request.path):
                return self.get_response(request)
            if module_denied:
                return handle_department_access_denied(request, module_key)
            if menu_denied:
                return handle_menu_access_denied(request, module_key, menu_key)

        return self.get_response(request)
