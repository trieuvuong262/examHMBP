from hrm.module_permissions import (
    handle_department_access_denied,
    resolve_module_from_request,
    user_can_access_module,
)


class DepartmentModuleAccessMiddleware:
    """Chặn URL module không thuộc quyền phòng ban của user."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated:
            module_key = resolve_module_from_request(
                request.path,
                request.GET.get('tab'),
            )
            if module_key and not user_can_access_module(user, module_key):
                return handle_department_access_denied(request, module_key)

        return self.get_response(request)
