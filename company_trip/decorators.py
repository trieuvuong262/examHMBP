"""Quyền vào Đăng ký du lịch theo menu Tiện ích."""

from functools import wraps

from django.contrib.auth.decorators import login_required

from company_trip.access import TRIP_MENU, TRIP_MODULE, trip_any_allowed
from hrm.menu_permissions import handle_menu_access_denied


def trip_perm_required(*actions):
    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if trip_any_allowed(request.user, actions):
                return view_func(request, *args, **kwargs)
            return handle_menu_access_denied(request, TRIP_MODULE, TRIP_MENU)

        return wrapper

    return decorator
