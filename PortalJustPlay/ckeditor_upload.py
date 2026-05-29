"""Upload/browse CKEditor — chỉ user có quyền quản trị portal."""

from functools import wraps

from ckeditor_uploader import views as ckeditor_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from assessment.decorators import _user_can_admin_request


def _editor_upload_access(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not _user_can_admin_request(request):
            raise PermissionDenied('Bạn không có quyền tải ảnh lên hệ thống.')
        return view_func(request, *args, **kwargs)

    return wrapper


upload = _editor_upload_access(ckeditor_views.upload)
browse = _editor_upload_access(ckeditor_views.browse)
