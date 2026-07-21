"""Decorator factories — kiểm tra quyền chi tiết theo module."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect

from hrm.module_permissions import (
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_export_module,
    user_can_print_module,
    user_can_update_module,
)
from hrm.permissions import portal_admin_denied_message

_ACTION_CHECKERS = {
    'view': user_can_access_module,
    'create': user_can_create_module,
    'update': user_can_update_module,
    'delete': user_can_delete_module,
    'export': user_can_export_module,
    'print': user_can_print_module,
    'edit': user_can_edit_module,
}


def module_action_required(module_key: str, action: str = 'view', *, redirect_to: str = 'home_portal'):
    """login_required + kiểm tra một quyền module (view/create/update/delete/export/print/edit)."""
    checker = _ACTION_CHECKERS.get(action, user_can_access_module)

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if checker(request.user, module_key):
                return view_func(request, *args, **kwargs)
            messages.error(request, portal_admin_denied_message())
            return redirect(redirect_to)

        return wrapper

    return decorator
