from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, Division, Profile, RoleModulePermission
from hrm.module_permissions import MODULE_HRM
from hrm.permissions import ROLE_DEPARTMENT_HEAD, ROLE_DIRECTOR, ROLE_DIVISION_HEAD, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from hrm.user_search import subordinate_candidate_queryset


class SubordinatePickerQuerysetTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='SX', sort_order=1)
        self.div_a = Division.objects.create(department=self.dept, name='May A', sort_order=1)
        self.div_b = Division.objects.create(department=self.dept, name='May B', sort_order=2)

        self.leader = self._user('leader', ROLE_TEAM_LEADER, self.dept, self.div_a)
        self.peer_div = self._user('peer_div', ROLE_EMPLOYEE, self.dept, self.div_b)
        self.same_div = self._user('same_div', ROLE_EMPLOYEE, self.dept, self.div_a)

    def _user(self, username, role, dept, division):
        user = User.objects.create_user(username=username, password='x')
        profile = Profile.objects.get(user=user)
        profile.role = role
        profile.department = dept
        profile.division = division
        profile.full_name = username
        profile.is_employed = True
        profile.save()
        return user

    def test_team_leader_sees_same_division_employees_only(self):
        qs = subordinate_candidate_queryset(
            exclude_user_id=self.leader.pk,
            manager_role=ROLE_TEAM_LEADER,
            department_id=self.dept.pk,
            division_id=self.div_a.pk,
        )
        ids = set(qs.values_list('pk', flat=True))
        self.assertIn(self.same_div.pk, ids)
        self.assertNotIn(self.peer_div.pk, ids)
        self.assertNotIn(self.leader.pk, ids)

    def test_keeps_extra_selected_when_outside_filter(self):
        qs = subordinate_candidate_queryset(
            exclude_user_id=self.leader.pk,
            manager_role=ROLE_TEAM_LEADER,
            department_id=self.dept.pk,
            division_id=self.div_a.pk,
            extra_user_ids=[self.peer_div.pk],
        )
        ids = set(qs.values_list('pk', flat=True))
        self.assertIn(self.peer_div.pk, ids)


class SubordinateCandidatesApiTests(TestCase):
    def setUp(self):
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_HRM: {'view': True, 'edit': True}}},
        )
        self.client = Client(HTTP_HOST='testserver')
        self.dept = Department.objects.create(name='API Dept', sort_order=1)
        self.admin = User.objects.create_user('api_admin', password='x', is_staff=True)
        Profile.objects.filter(user=self.admin).update(
            role=ROLE_DIRECTOR,
            is_employed=True,
            permission_group=None,
        )

        self.emp = User.objects.create_user('api_emp', password='x')
        emp_profile = Profile.objects.get(user=self.emp)
        emp_profile.role = ROLE_EMPLOYEE
        emp_profile.department = self.dept
        emp_profile.is_employed = True
        emp_profile.save()

    def test_api_returns_department_head_candidates(self):
        self.client.force_login(self.admin)
        url = reverse('user_subordinate_candidates')
        response = self.client.get(url, {
            'role': ROLE_DEPARTMENT_HEAD,
            'department': self.dept.pk,
            'exclude_user_id': self.admin.pk,
        })
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertGreaterEqual(payload['count'], 1)
        ids = {row['id'] for row in payload['users']}
        self.assertIn(self.emp.pk, ids)
