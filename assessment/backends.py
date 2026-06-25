# assessment/backends.py
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

from audit.login_security import is_user_locked, resolve_user_by_login_identifier

UserModel = get_user_model()


class UsernameModelBackend(ModelBackend):
    """Đăng nhập Portal chỉ bằng username (có kiểm tra khóa tài khoản)."""
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