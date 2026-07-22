# assessment/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

from audit.login_security import is_user_locked, resolve_user_by_login_identifier
from hrm.user_search import is_protected_system_user

UserModel = get_user_model()


class UsernameModelBackend(ModelBackend):
    """Đăng nhập Portal chỉ bằng username (có kiểm tra khóa tài khoản)."""

    def user_can_authenticate(self, user):
        """Chặn user nghỉ làm — kể cả khi is_active bị lệch với is_employed."""
        if not super().user_can_authenticate(user):
            return False
        if is_protected_system_user(user):
            return True
        profile = getattr(user, 'profile', None)
        if profile is None:
            try:
                from hrm.models import Profile
                profile = Profile.objects.filter(user_id=user.pk).first()
            except Exception:
                return True
        if profile is not None and not profile.is_employed:
            return False
        return True

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)

        user = resolve_user_by_login_identifier(username or '')
        if user is None:
            UserModel().set_password(password)
            return None

        if is_user_locked(user):
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
