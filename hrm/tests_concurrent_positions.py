"""Kiểm thử vị trí kiêm nhiệm — quyền tổ chức và sơ đồ."""

import json

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import QueryDict
from django.test import Client, TestCase
from django.urls import reverse

from hrm.concurrent_positions import (
    auto_managed_user_ids,
    effective_department_ids,
    effective_roles,
    find_manager_with_subordinate,
    get_effective_subordinate_users,
    heads_for_division,
)
from hrm.forms import ProfileConcurrentPositionEditFormSet, ProfileConcurrentPositionForm
from hrm.models import Department, Division, Profile, ProfileConcurrentPosition, RoleModulePermission
from hrm.module_permissions import MODULE_HRM
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

    def test_new_slot_defaults_active(self):
        form = ProfileConcurrentPositionForm()
        self.assertTrue(form.fields['is_active'].initial)

    def test_reuse_inactive_slot_on_save(self):
        inactive = ProfileConcurrentPosition.objects.create(
            profile=self.user.profile,
            department=self.dept_a,
            division=None,
            job_position='Trưởng phòng',
            role=ROLE_DEPARTMENT_HEAD,
            is_active=False,
        )
        post_data = QueryDict(mutable=True)
        post_data.update({
            'concurrent-0-department': str(self.dept_a.pk),
            'concurrent-0-division': '',
            'concurrent-0-job_position': 'Trưởng phòng',
            'concurrent-0-job_title': 'TP R&D',
            'concurrent-0-role': ROLE_DEPARTMENT_HEAD,
            'concurrent-0-sort_order': '0',
            'concurrent-0-is_active': 'on',
            'concurrent-0-notes': '',
        })
        form = ProfileConcurrentPositionForm(
            data=post_data,
            instance=ProfileConcurrentPosition(profile=self.user.profile),
            prefix='concurrent-0',
        )
        self.assertTrue(form.is_valid(), form.errors)
        slot = form.save()
        self.assertEqual(slot.pk, inactive.pk)
        self.assertTrue(slot.is_active)
        self.assertEqual(
            ProfileConcurrentPosition.objects.filter(profile=self.user.profile).count(),
            1,
        )

    def test_edit_formset_hides_inactive_slots(self):
        ProfileConcurrentPosition.objects.create(
            profile=self.user.profile,
            department=self.dept_a,
            job_position='Trưởng phòng',
            role=ROLE_DEPARTMENT_HEAD,
            is_active=True,
        )
        ProfileConcurrentPosition.objects.create(
            profile=self.user.profile,
            department=self.dept_b,
            job_position='Trưởng phòng',
            role=ROLE_DEPARTMENT_HEAD,
            is_active=False,
        )
        formset = ProfileConcurrentPositionEditFormSet(
            instance=self.user.profile,
            prefix='concurrent',
        )
        self.assertEqual(len(formset.forms), 1)
        self.assertEqual(formset.forms[0].instance.department_id, self.dept_a.pk)


def _slot_post(prefix, dept, *, division=None, job_position='Trưởng phòng', role=ROLE_DEPARTMENT_HEAD,
               is_active=True, slot_id='', extra=None):
    data = {
        'form_prefix': prefix,
        f'{prefix}-department': str(dept.pk),
        f'{prefix}-division': str(division.pk) if division else '',
        f'{prefix}-job_position': job_position,
        f'{prefix}-job_title': '',
        f'{prefix}-role': role,
        f'{prefix}-sort_order': '0',
        f'{prefix}-notes': '',
    }
    if slot_id:
        data['slot_id'] = str(slot_id)
        data[f'{prefix}-id'] = str(slot_id)
    if is_active:
        data[f'{prefix}-is_active'] = 'on'
    if extra:
        data.update(extra)
    return data


class ConcurrentSlotApiTests(TestCase):
    def setUp(self):
        RoleModulePermission.objects.update_or_create(
            role=ROLE_DIRECTOR,
            defaults={'module_permissions': {MODULE_HRM: {'view': True, 'edit': True}}},
        )
        self.dept_a = Department.objects.create(name='CP Dept A', sort_order=1)
        self.dept_b = Department.objects.create(name='CP Dept B', sort_order=2)
        self.admin = User.objects.create_user('cp_admin', password='x', is_staff=True)
        _profile(self.admin, full_name='CP Admin', role=ROLE_DIRECTOR, is_employed=True)
        self.target = User.objects.create_user('cp_target', password='x')
        _profile(self.target, full_name='CP Target', department=self.dept_a, is_employed=True)
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.admin)
        self.save_url = reverse('user_concurrent_slot_save', args=[self.target.id])

    def test_ajax_create_slot(self):
        response = self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_b))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['slot_id'])
        self.assertEqual(data['concurrent_active_count'], 1)
        slot = ProfileConcurrentPosition.objects.get(pk=data['slot_id'])
        self.assertTrue(slot.is_active)
        self.assertEqual(slot.department_id, self.dept_b.pk)

    def test_ajax_create_second_slot_no_duplicate_on_profile_save(self):
        r1 = self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_a))
        r2 = self.client.post(self.save_url, _slot_post('concurrent-1', self.dept_b))
        id1 = json.loads(r1.content)['slot_id']
        id2 = json.loads(r2.content)['slot_id']
        self.assertEqual(
            ProfileConcurrentPosition.objects.filter(profile=self.target.profile, is_active=True).count(),
            2,
        )
        response = self.client.post(reverse('user_edit', args=[self.target.id]), {
            'username': 'cp_target',
            'email': '',
            'full_name': 'CP Target',
            'role': ROLE_EMPLOYEE,
            'is_employed': '1',
            'concurrent-TOTAL_FORMS': '3',
            'concurrent-INITIAL_FORMS': '1',
            'concurrent-MIN_NUM_FORMS': '0',
            'concurrent-MAX_NUM_FORMS': '1000',
            f'concurrent-0-id': str(id1),
            'concurrent-0-department': str(self.dept_a.pk),
            'concurrent-0-division': '',
            'concurrent-0-job_position': 'Trưởng phòng',
            'concurrent-0-job_title': '',
            'concurrent-0-role': ROLE_DEPARTMENT_HEAD,
            'concurrent-0-sort_order': '0',
            'concurrent-0-is_active': 'on',
            'concurrent-0-notes': '',
            'concurrent-1-department': str(self.dept_b.pk),
            'concurrent-1-division': '',
            'concurrent-1-job_position': 'Trưởng phòng',
            'concurrent-1-job_title': '',
            'concurrent-1-role': ROLE_DEPARTMENT_HEAD,
            'concurrent-1-sort_order': '0',
            'concurrent-1-is_active': 'on',
            'concurrent-1-notes': '',
            'concurrent-2-department': str(self.dept_b.pk),
            'concurrent-2-division': '',
            'concurrent-2-job_position': 'Trùng slot ảo',
            'concurrent-2-role': ROLE_DEPARTMENT_HEAD,
            'concurrent-2-is_active': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            ProfileConcurrentPosition.objects.filter(profile=self.target.profile, is_active=True).count(),
            2,
        )
        self.assertTrue(ProfileConcurrentPosition.objects.filter(pk=id1, is_active=True).exists())
        self.assertTrue(ProfileConcurrentPosition.objects.filter(pk=id2, is_active=True).exists())

    def test_ajax_delete_slot(self):
        create = self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_b))
        slot_id = json.loads(create.content)['slot_id']
        response = self.client.post(self.save_url, {
            'form_prefix': 'concurrent-0',
            'slot_action': 'delete',
            'slot_id': str(slot_id),
            f'concurrent-0-id': str(slot_id),
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data['status'], 'ok')
        self.assertTrue(data['deleted'])
        self.assertEqual(data['concurrent_active_count'], 0)
        self.assertFalse(ProfileConcurrentPosition.objects.filter(pk=slot_id).exists())

    def test_ajax_delete_requires_saved_slot(self):
        response = self.client.post(self.save_url, {
            'form_prefix': 'concurrent-0',
            'slot_action': 'delete',
        })
        self.assertEqual(response.status_code, 400)

    def test_ajax_reject_duplicate_active_slot(self):
        self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_a, job_position='Trưởng phòng'))
        response = self.client.post(
            self.save_url,
            _slot_post('concurrent-1', self.dept_a, job_position='Trưởng phòng'),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            ProfileConcurrentPosition.objects.filter(
                profile=self.target.profile,
                department=self.dept_a,
                is_active=True,
            ).count(),
            1,
        )

    def test_ajax_update_existing_slot(self):
        create = self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_a))
        slot_id = json.loads(create.content)['slot_id']
        response = self.client.post(
            self.save_url,
            _slot_post(
                'concurrent-0',
                self.dept_a,
                slot_id=slot_id,
                extra={f'concurrent-0-job_title': 'TP Cập nhật'},
            ),
        )
        self.assertEqual(response.status_code, 200)
        slot = ProfileConcurrentPosition.objects.get(pk=slot_id)
        self.assertEqual(slot.job_title, 'TP Cập nhật')
        self.assertEqual(
            ProfileConcurrentPosition.objects.filter(profile=self.target.profile).count(),
            1,
        )

    def test_edit_form_renders_delete_field(self):
        self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_b))
        response = self.client.get(reverse('user_edit', args=[self.target.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'concurrent-0-DELETE')
        self.assertContains(response, 'jp-concurrent-slot-delete')
        self.assertContains(response, 'disableConcurrentFieldsForSubmit')

    def test_user_list_shows_active_concurrent_count(self):
        self.client.post(self.save_url, _slot_post('concurrent-0', self.dept_b))
        self.client.post(self.save_url, _slot_post('concurrent-1', self.dept_a))
        response = self.client.get(reverse('user_list'))
        self.assertContains(response, '+2 kiêm nhiệm')


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
