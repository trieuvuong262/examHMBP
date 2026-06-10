from hrm.menu_permissions import (
    handle_menu_access_denied,
    resolve_menu_from_request,
    user_can_access_menu,
)
from hrm.module_permissions import (
    handle_department_access_denied,
    user_can_access_module,
)


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
            if module_key and not user_can_access_module(user, module_key):
                return handle_department_access_denied(request, module_key)
            if module_key and menu_key and not user_can_access_menu(user, module_key, menu_key):
                return handle_menu_access_denied(request, module_key, menu_key)

        return self.get_response(request)
