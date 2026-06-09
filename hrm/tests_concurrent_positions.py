"""Kiểm thử vị trí kiêm nhiệm — quyền tổ chức và sơ đồ."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase

from hrm.concurrent_positions import (
    auto_managed_user_ids,
    effective_department_ids,
    effective_roles,
    find_manager_with_subordinate,
    get_effective_subordinate_users,
    heads_for_division,
)
from hrm.models import Department, Division, Profile, ProfileConcurrentPosition
from hrm.org_structure import _division_head_profiles, _employee_nodes
from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    get_report_team_users,
    get_task_assignable_users,
    is_department_head,
    is_division_head,
)
from service_requests.workflow import (
    department_has_department_heads,
    department_has_team_leaders,
    find_department_head_manager,
    find_division_head_manager,
    find_team_leader,
)


def _profile(user, **kwargs):
    prof, _ = Profile.objects.get_or_create(user=user)
    for key, value in kwargs.items():
        setattr(prof, key, value)
    prof.save()
    user.refresh_from_db()
    return prof


class ProfileConcurrentPositionModelTests(TestCase):
    def setUp(self):
        self.dept_a = Department.objects.create(name='R&D Test', sort_order=1)
        self.dept_b = Department.objects.create(name='KD Test', sort_order=2)
        self.div_rd = Division.objects.create(
            name='BP R&D', department=self.dept_a, sort_order=1,
        )
        self.div_wrong = Division.objects.create(
            name='BP KD', department=self.dept_b, sort_order=1,
        )
        self.user = User.objects.create_user('cp_user', password='x')
        _profile(self.user, full_name='CP User', department=self.dept_b, is_employed=True)

    def test_division_must_belong_to_department(self):
        slot = ProfileConcurrentPosition(
            profile=self.user.profile,
            department=self.dept_a,
            division=self.div_wrong,
            job_position='Trưởng phòng',
            role=ROLE_DIVISION_HEAD,
        )
        with self.assertRaises(ValidationError):
            slot.full_clean()

    def test_active_slot_unique(self):
        ProfileConcurrentPosition.objects.create(
            profile=self.user.profile,
            department=self.dept_a,
            division=self.div_rd,
            job_position='Trưởng bộ phận',
            role=ROLE_DIVISION_HEAD,
            is_active=True,
        )
        dup = ProfileConcurrentPosition(
            profile=self.user.profile,
            department=self.dept_a,
            division=self.div_rd,
            job_position='Trưởng bộ phận',
            role=ROLE_DIVISION_HEAD,
            is_active=True,
        )
        with self.assertRaises(Exception):
            dup.save()


class EffectiveOrgContextTests(TestCase):
    def setUp(self):
        self.dept_rd = Department.objects.create(name='R&D Conc Test', sort_order=901)
        self.dept_hc = Department.objects.create(name='HC Conc Test', sort_order=902)
        self.div_rd = Division.objects.create(name='Lab Conc', department=self.dept_rd, sort_order=1)

        self.tgd = User.objects.create_user('tgd', password='x')
        _profile(
            self.tgd,
            full_name='TGD',
            department=self.dept_hc,
            role=ROLE_DIRECTOR,
            is_employed=True,
        )
        ProfileConcurrentPosition.objects.create(
            profile=self.tgd.profile,
            department=self.dept_rd,
            division=self.div_rd,
            job_position='Trưởng phòng',
            job_title='TP R&D',
            role=ROLE_DIVISION_HEAD,
        )

        self.rd_emp = User.objects.create_user('rd_emp', password='x')
        _profile(
            self.rd_emp,
            full_name='NV R&D',
            department=self.dept_rd,
            division=self.div_rd,
            job_position='Nhân viên',
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )

    def test_effective_roles_union(self):
        roles = effective_roles(self.tgd)
        self.assertIn(ROLE_DIRECTOR, roles)
        self.assertIn(ROLE_DIVISION_HEAD, roles)

    def test_effective_department_ids(self):
        ids = effective_department_ids(self.tgd)
        self.assertIn(self.dept_hc.pk, ids)
        self.assertIn(self.dept_rd.pk, ids)

    def test_director_concurrent_division_head_assignable_users(self):
        assignable = set(
            get_task_assignable_users(self.tgd).values_list('pk', flat=True),
        )
        self.assertIn(self.rd_emp.pk, assignable)

    def test_auto_scope_division_head(self):
        managed = auto_managed_user_ids(self.tgd)
        self.assertIn(self.rd_emp.pk, managed)

    def test_is_division_head_via_concurrent(self):
        self.assertTrue(is_division_head(self.tgd))


class OrgStructureConcurrentTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='QA Dept Conc', sort_order=903)
        self.div = Division.objects.create(name='QA Div Conc', department=self.dept, sort_order=1)
        self.head = User.objects.create_user('qa_head', password='x')
        _profile(
            self.head,
            full_name='QA Head',
            department=self.dept,
            division=None,
            role=ROLE_DIRECTOR,
            is_employed=True,
        )
        ProfileConcurrentPosition.objects.create(
            profile=self.head.profile,
            department=self.dept,
            division=self.div,
            job_position='Trưởng bộ phận',
            role=ROLE_DIVISION_HEAD,
        )

    def test_concurrent_division_head_in_org_chart(self):
        qs = _division_head_profiles(self.dept.pk, self.div.pk)
        self.assertTrue(qs.filter(user=self.head).exists())

    def test_employee_node_marks_concurrent(self):
        nodes = _employee_nodes(self.dept.pk, self.div.pk, 'Trưởng bộ phận')
        match = [n for n in nodes if n.get('user_id') == self.head.pk]
        self.assertEqual(len(match), 1)
        self.assertTrue(match[0].get('is_concurrent'))


class DepartmentHeadRoleTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Dept Head Test', sort_order=910)
        self.div = Division.objects.create(name='Div DH', department=self.dept, sort_order=1)

        self.dept_head = User.objects.create_user('dept_head', password='x')
        _profile(
            self.dept_head,
            full_name='Trưởng phòng',
            department=self.dept,
            role=ROLE_DEPARTMENT_HEAD,
            is_employed=True,
        )

        self.div_head = User.objects.create_user('div_head_sub', password='x')
        _profile(
            self.div_head,
            full_name='TBP',
            department=self.dept,
            division=self.div,
            role=ROLE_DIVISION_HEAD,
            is_employed=True,
        )
        self.dept_head.profile.subordinates.add(self.div_head)

        self.emp = User.objects.create_user('dept_emp', password='x')
        _profile(
            self.emp,
            full_name='NV',
            department=self.dept,
            division=self.div,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )

    def test_is_department_head_primary(self):
        self.assertTrue(is_department_head(self.dept_head))

    def test_department_head_manual_subordinate_in_reports(self):
        subs = set(get_report_team_users(self.dept_head).values_list('pk', flat=True))
        self.assertIn(self.div_head.pk, subs)

    def test_department_has_heads_helper(self):
        self.assertTrue(department_has_department_heads(self.dept))

    def test_workflow_finds_department_head(self):
        found = find_department_head_manager(self.emp)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, self.dept_head.pk)


class ConcurrentSlotSubordinatesTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Slot Sub Test', sort_order=911)
        self.div = Division.objects.create(name='Slot Div', department=self.dept, sort_order=1)

        self.manager = User.objects.create_user('slot_mgr', password='x')
        _profile(
            self.manager,
            full_name='Manager',
            department=Department.objects.create(name='Other Dept', sort_order=912),
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.slot = ProfileConcurrentPosition.objects.create(
            profile=self.manager.profile,
            department=self.dept,
            division=self.div,
            job_position='Trưởng bộ phận',
            role=ROLE_DIVISION_HEAD,
        )

        self.sub = User.objects.create_user('slot_sub', password='x')
        _profile(
            self.sub,
            full_name='Sub Slot',
            department=self.dept,
            division=self.div,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        self.slot.subordinates.add(self.sub)

    def test_concurrent_slot_subordinates_in_effective_team(self):
        subs = set(get_report_team_users(self.manager).values_list('pk', flat=True))
        self.assertIn(self.sub.pk, subs)


class WorkflowConcurrentTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Mua hang Conc', sort_order=904)
        self.div = Division.objects.create(name='Thu mua Conc', department=self.dept, sort_order=1)

        self.tl = User.objects.create_user('tl_conc', password='x')
        _profile(
            self.tl,
            full_name='TL Kiêm',
            department=Department.objects.create(name='Khac Conc', sort_order=905),
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )
        ProfileConcurrentPosition.objects.create(
            profile=self.tl.profile,
            department=self.dept,
            division=self.div,
            job_position='Tổ trưởng',
            role=ROLE_TEAM_LEADER,
        )

        self.requester = User.objects.create_user('req', password='x')
        _profile(
            self.requester,
            full_name='Requester',
            department=self.dept,
            division=self.div,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )

    def test_department_has_concurrent_team_leader(self):
        self.assertTrue(department_has_team_leaders(self.dept))

    def test_find_team_leader_via_auto_scope(self):
        found = find_team_leader(self.requester)
        self.assertIsNotNone(found)
        self.assertEqual(found.pk, self.tl.pk)

    def test_find_manager_with_subordinate_helper(self):
        found = find_manager_with_subordinate(self.requester, ROLE_TEAM_LEADER)
        self.assertEqual(found.pk, self.tl.pk)


class KpiConcurrentManagerTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='KPI Dept Conc', sort_order=906)
        self.div = Division.objects.create(name='KPI Div Conc', department=self.dept, sort_order=1)

        self.mgr = User.objects.create_user('kpi_mgr', password='x')
        _profile(
            self.mgr,
            full_name='Mgr Kiêm',
            department=Department.objects.create(name='GĐ Conc', sort_order=907),
            role=ROLE_DIRECTOR,
            is_employed=True,
        )
        ProfileConcurrentPosition.objects.create(
            profile=self.mgr.profile,
            department=self.dept,
            division=self.div,
            job_position='Trưởng bộ phận',
            role=ROLE_DIVISION_HEAD,
        )

        self.sub = User.objects.create_user('kpi_sub', password='x')
        _profile(
            self.sub,
            full_name='Sub',
            department=self.dept,
            division=self.div,
            role=ROLE_EMPLOYEE,
            is_employed=True,
        )

    def test_effective_subordinates_include_auto_scope(self):
        subs = set(get_effective_subordinate_users(self.mgr).values_list('pk', flat=True))
        self.assertIn(self.sub.pk, subs)

    def test_division_head_manager_resolution(self):
        dh = find_division_head_manager(self.sub)
        self.assertIsNotNone(dh)
        self.assertEqual(dh.pk, self.mgr.pk)
