from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.test import TestCase

from assessment.backends import UsernameModelBackend
from hrm.models import Profile
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE


class ResignedEmployeeLoginTests(TestCase):
    """Nhân viên trạng thái nghỉ làm không được đăng nhập Portal."""

    def setUp(self):
        self.backend = UsernameModelBackend()

    def _make_user(self, username, *, role=ROLE_EMPLOYEE, is_employed=True, password='secret123'):
        user = User.objects.create_user(username=username, password=password)
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.full_name = username
        profile.role = role
        profile.is_employed = is_employed
        profile.save()
        user.refresh_from_db()
        return user

    def test_employed_employee_can_login(self):
        self._make_user('nv_active', is_employed=True)
        user = authenticate(username='nv_active', password='secret123')
        self.assertIsNotNone(user)

    def test_resigned_employee_cannot_login(self):
        self._make_user('nv_quit', is_employed=False)
        user = authenticate(username='nv_quit', password='secret123')
        self.assertIsNone(user)

    def test_resigned_director_cannot_login(self):
        """Trước đây Giám đốc (superuser) vẫn đăng nhập được dù đã nghỉ."""
        director = self._make_user('gd_quit', role=ROLE_DIRECTOR, is_employed=False)
        self.assertTrue(director.is_superuser)
        self.assertFalse(director.is_active)
        user = authenticate(username='gd_quit', password='secret123')
        self.assertIsNone(user)

    def test_desynced_is_active_still_blocked(self):
        """is_employed=False nhưng is_active=True (lệch dữ liệu) vẫn bị chặn."""
        user = self._make_user('nv_desync', is_employed=False)
        User.objects.filter(pk=user.pk).update(is_active=True)
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(user.profile.is_employed)
        self.assertFalse(self.backend.user_can_authenticate(user))
        self.assertIsNone(authenticate(username='nv_desync', password='secret123'))

    def test_mark_employed_false_deactivates_user(self):
        user = self._make_user('nv_toggle', is_employed=True)
        self.assertTrue(user.is_active)
        profile = user.profile
        profile.is_employed = False
        profile.save()
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertIsNone(authenticate(username='nv_toggle', password='secret123'))