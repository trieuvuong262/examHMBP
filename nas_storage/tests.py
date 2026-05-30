from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from hrm.models import Department, Profile
from hrm.module_permissions import MODULE_NAS_STORAGE, resolve_module_from_request
from nas_storage.nas_paths import (
    NasPathError,
    department_folder_code,
    get_user_nas_roots,
    normalize_rel_path,
    resolve_nas_path,
)


class NasPathTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='HÀNH CHÍNH NHÂN SỰ', sort_order=1)
        self.user = User.objects.create_user(username='Annt', password='test')
        Profile.objects.create(user=self.user, full_name='Test User', department=self.dept)

    def test_department_folder_code(self):
        self.assertEqual(department_folder_code('HÀNH CHÍNH NHÂN SỰ'), 'HCNS')

    def test_user_roots(self):
        roots = get_user_nas_roots(self.user)
        self.assertEqual(len(roots), 2)
        self.assertEqual(roots[0].rel_path, 'HCNS/Annt')
        self.assertEqual(roots[1].rel_path, 'HCNS/_CHUNG')

    def test_normalize_rejects_traversal(self):
        with self.assertRaises(NasPathError):
            normalize_rel_path('HCNS/../IT/secret')

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-test')
    def test_resolve_allowed_path(self):
        import os
        os.makedirs('/tmp/nas-test/HCNS/Annt', exist_ok=True)
        path = resolve_nas_path(self.user, 'HCNS/Annt')
        self.assertTrue(str(path).endswith('HCNS/Annt'))

    @override_settings(NAS_MOUNT_ROOT='/tmp/nas-test')
    def test_resolve_denies_other_dept(self):
        import os
        os.makedirs('/tmp/nas-test/IT/Other', exist_ok=True)
        with self.assertRaises(NasPathError):
            resolve_nas_path(self.user, 'IT/Other')


class NasModuleRegistrationTests(TestCase):
    def test_resolve_module_from_url(self):
        self.assertEqual(resolve_module_from_request('/thu-muc-nas/'), MODULE_NAS_STORAGE)
        self.assertEqual(resolve_module_from_request('/thu-muc-nas/?path=HCNS/Annt'), MODULE_NAS_STORAGE)


class NasBrowseViewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='IT', sort_order=1)
        self.user = User.objects.create_user(username='VuongIT', password='test')
        Profile.objects.create(user=self.user, full_name='Vuong', department=self.dept)

    def test_browse_requires_login(self):
        response = self.client.get(reverse('nas_storage:browse'))
        self.assertEqual(response.status_code, 302)
