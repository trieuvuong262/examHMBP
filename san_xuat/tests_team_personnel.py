from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Division, PermissionGroup, Profile, ProfileConcurrentPosition
from hrm.module_permissions import MODULE_SAN_XUAT
from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import DailyWorkReport, DailyWorkReportLine
from san_xuat.hub_models import (
    SxMoProcessAssignee,
    SxMoProcessStep,
    SxProductionOrder,
    SxTeamDivisionMap,
    SxTeamPersonnelSkill,
    SxTeamWorkClose,
)
from san_xuat.services.planning import PlanningError
from san_xuat.services.progress_template import step_by_key
from san_xuat.services.team_personnel import (
    build_team_personnel_board,
    can_edit_team_personnel,
    upsert_team_personnel_skill,
)


class TeamPersonnelTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='SX Personnel', sort_order=1)
        DepartmentMenuPermission.objects.create(department=self.dept, modules=[MODULE_SAN_XUAT])
        self.div_cat = Division.objects.create(department=self.dept, name='Cat trai', sort_order=1)
        self.div_may = Division.objects.create(department=self.dept, name='May 1', sort_order=2)
        SxTeamDivisionMap.objects.create(team_slug='cat', division=self.div_cat, is_active=True, is_demo=False)

        view_menu = {
            'view': True, 'create': False, 'update': False, 'delete': False, 'export': False, 'print': False,
        }
        self.group = PermissionGroup.objects.create(
            slug='sx-tw-cat-view',
            name='SX Cat xem',
            module_permissions={
                MODULE_SAN_XUAT: {
                    **view_menu,
                    'menus': {'team_work_cat': dict(view_menu)},
                },
            },
        )
        self.leader = self._user('tw_leader', ROLE_TEAM_LEADER, self.div_cat)
        self.member = self._user('tw_member', ROLE_EMPLOYEE, self.div_cat)
        self.concurrent = self._user('tw_concurrent', ROLE_EMPLOYEE, self.div_may)
        ProfileConcurrentPosition.objects.create(
            profile=self.concurrent.profile,
            department=self.dept,
            division=self.div_cat,
            job_position='Tho cat kiem',
            role=ROLE_EMPLOYEE,
            is_active=True,
        )
        self.other_leader = self._user('tw_other_ldr', ROLE_TEAM_LEADER, self.div_may)
        self.manager = self._user('tw_manager', ROLE_DIVISION_HEAD, self.div_may)
        self.outsider = self._user('tw_outsider', ROLE_EMPLOYEE, self.div_may)
        deny_group = PermissionGroup.objects.create(
            slug='sx-tw-no-cat',
            name='SX khong co cat',
            module_permissions={
                MODULE_SAN_XUAT: {
                    **view_menu,
                    'menus': {'overview': dict(view_menu)},
                },
            },
        )
        self.no_menu = User.objects.create_user(username='tw_nomnu', password='test')
        Profile.objects.filter(user=self.no_menu).update(
            department=self.dept,
            division=self.div_may,
            role=ROLE_EMPLOYEE,
            is_employed=True,
            permission_group=deny_group,
        )
        self.no_menu.refresh_from_db()
        self.client = Client(HTTP_HOST='testserver')
        self.url = reverse('san_xuat:team_work_personnel', kwargs={'slug': 'cat'})

    def _user(self, username, role, division):
        user = User.objects.create_user(username=username, password='test')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            division=division,
            role=role,
            full_name=username.replace('_', ' ').title(),
            employee_code=f'NS-{username[-4:].upper()}',
            is_employed=True,
            on_probation=(role == ROLE_EMPLOYEE),
            permission_group=self.group,
            job_position='Tho cat' if division == self.div_cat else 'Tho may',
        )
        user.refresh_from_db()
        return user

    def _mo(self, code='LSX-TW-P1'):
        return SxProductionOrder.objects.create(
            code=code,
            product_code='JP-TEE-001',
            product_name='Ao test',
            qty=Decimal('100'),
            order_date=timezone.localdate(),
            status=SxProductionOrder.STATUS_RELEASED,
            is_demo=False,
        )

    def test_roster_uses_mapped_divisions_and_concurrent(self):
        board = build_team_personnel_board(slug='cat')
        ids = {row.user_id for row in board.rows}
        self.assertIn(self.leader.pk, ids)
        self.assertIn(self.member.pk, ids)
        self.assertIn(self.concurrent.pk, ids)
        self.assertNotIn(self.outsider.pk, ids)
        self.assertNotIn(self.other_leader.pk, ids)
        self.assertEqual(board.total, 3)
        self.assertTrue(board.mapped)

    def test_can_edit_team_leader_of_team_and_higher(self):
        self.assertTrue(can_edit_team_personnel(self.leader, 'cat'))
        self.assertTrue(can_edit_team_personnel(self.manager, 'cat'))
        self.assertFalse(can_edit_team_personnel(self.member, 'cat'))
        self.assertFalse(can_edit_team_personnel(self.other_leader, 'cat'))
        self.assertFalse(can_edit_team_personnel(self.outsider, 'cat'))

    def test_upsert_skill_and_reject_outsider(self):
        rec = upsert_team_personnel_skill(
            slug='cat',
            user_id=self.member.pk,
            process_keys=['cat_ao', 'cat_quan', 'may_rap_vai'],
            skill_level='B',
            machines='Ban cat',
            is_multiskill=True,
            notes='Lam duoc trai vai',
            updated_by=self.leader,
        )
        self.assertEqual(rec.skill_level, 'B')
        self.assertEqual(rec.process_keys, ['cat_ao', 'cat_quan'])
        self.assertTrue(rec.is_multiskill)
        with self.assertRaises(PlanningError):
            upsert_team_personnel_skill(slug='cat', user_id=self.outsider.pk, skill_level='A')

    def test_assignment_and_output_summary(self):
        mo = self._mo()
        step = SxMoProcessStep.objects.create(
            production_order=mo,
            sequence=10,
            process_name=step_by_key('cat_ao').label,
            status=SxMoProcessStep.STATUS_IN_PROGRESS,
        )
        SxMoProcessAssignee.objects.create(mo_process_step=step, user=self.member)
        closed_mo = self._mo('LSX-TW-P2')
        closed_step = SxMoProcessStep.objects.create(
            production_order=closed_mo,
            sequence=10,
            process_name=step_by_key('cat_quan').label,
            status=SxMoProcessStep.STATUS_DONE,
        )
        SxMoProcessAssignee.objects.create(mo_process_step=closed_step, user=self.member)
        SxTeamWorkClose.objects.create(
            production_order=closed_mo,
            team_slug='cat',
            is_demo=False,
        )
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=date.today(),
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        DailyWorkReportLine.objects.create(report=report, area='CUT', quantity=40, product_name='Ao')

        board = build_team_personnel_board(slug='cat')
        row = next(r for r in board.rows if r.user_id == self.member.pk)
        self.assertEqual(row.open_jobs, 1)
        self.assertEqual(row.open_steps, 1)
        self.assertEqual(row.closed_jobs, 1)
        self.assertEqual(row.reports_14d, 1)
        self.assertEqual(row.qty_14d, Decimal('40'))
        self.assertEqual(board.busy, 1)
        self.assertEqual(board.idle, board.total - 1)

    def test_view_ok_for_team_menu_and_denied_without(self):
        self.client.force_login(self.leader)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Quản lý nhân sự')
        self.assertContains(response, self.member.profile.full_name)

        self.client.force_login(self.no_menu)
        denied = self.client.get(self.url)
        self.assertEqual(denied.status_code, 302)

    def test_leader_can_post_skill_employee_cannot(self):
        self.client.force_login(self.member)
        blocked = self.client.post(self.url, {
            'user_id': self.member.pk,
            'skill_level': 'A',
            'process_keys': ['cat_ao'],
        })
        self.assertEqual(blocked.status_code, 302)
        self.assertFalse(SxTeamPersonnelSkill.objects.filter(user=self.member, team_slug='cat').exists())

        self.client.force_login(self.leader)
        ok = self.client.post(self.url, {
            'user_id': self.member.pk,
            'skill_level': 'A',
            'process_keys': ['cat_ao'],
            'machines': 'May cat',
            'is_multiskill': '1',
            'notes': 'OK',
        })
        self.assertEqual(ok.status_code, 302)
        rec = SxTeamPersonnelSkill.objects.get(user=self.member, team_slug='cat')
        self.assertEqual(rec.skill_level, 'A')
        self.assertEqual(rec.process_keys, ['cat_ao'])
        self.assertTrue(rec.is_multiskill)
        self.assertEqual(rec.machines, 'May cat')
