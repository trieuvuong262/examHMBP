from django.contrib.auth.models import User
from django.test import TestCase

from hrm.models import Department, Division, Profile
from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
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
