from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from utilities.portal_push_eligibility import (
    user_meal_push_eligible,
    user_portal_push_debug,
    user_portal_push_eligible,
)


@override_settings(
    WEBPUSH_VAPID_PUBLIC_KEY='test-public',
    WEBPUSH_VAPID_PRIVATE_KEY='test-private',
)
class PortalPushEligibilityTests(TestCase):
    def setUp(self):
        self.sx_dept = Department.objects.create(
            name='SX Push Eligibility',
            sort_order=1,
            report_profile='PRODUCTION',
        )
        self.vp_dept = Department.objects.create(name='VP Push Eligibility', sort_order=2)
        DepartmentMenuPermission.objects.create(department=self.sx_dept, modules=['utilities', 'announcements'])
        DepartmentMenuPermission.objects.create(department=self.vp_dept, modules=['announcements'])
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'utilities': {'view': True, 'edit': True},
                    'announcements': {'view': True},
                },
            },
        )
        self.sx_user = User.objects.create_user(username='sx', password='x')
        Profile.objects.filter(user=self.sx_user).update(
            department=self.sx_dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.sx_user.refresh_from_db()
        self.vp_user = User.objects.create_user(username='vp', password='x')
        Profile.objects.filter(user=self.vp_user).update(
            department=self.vp_dept,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.vp_user.refresh_from_db()

    def test_sx_user_meal_and_portal_eligible(self):
        self.assertTrue(user_meal_push_eligible(self.sx_user))
        self.assertTrue(user_portal_push_eligible(self.sx_user))

    def test_vp_user_only_portal_eligible(self):
        self.assertFalse(user_meal_push_eligible(self.vp_user))
        self.assertTrue(user_portal_push_eligible(self.vp_user))

    def test_push_debug_staff_only(self):
        self.assertFalse(user_portal_push_debug(self.sx_user))
        self.sx_user.is_staff = True
        self.assertTrue(user_portal_push_debug(self.sx_user))
