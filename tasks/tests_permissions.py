from datetime import date

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, PermissionGroup, Profile
from hrm.module_permissions import MODULE_TASKS
from hrm.permissions import ROLE_DIRECTOR, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from hrm.group_permissions import normalize_group_permissions, permissions_from_legacy_role
from tasks.models import WorkTask, WorkTaskRecurrence


class TasksGranularPermissionTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Tasks Perm Dept', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=self.dept,
            modules=['tasks'],
        )

        base = normalize_group_permissions(permissions_from_legacy_role(ROLE_EMPLOYEE))

        view_only = dict(base)
        view_only[MODULE_TASKS] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_view = PermissionGroup.objects.create(
            slug='test-tasks-view',
            name='Tasks view only',
            module_permissions=view_only,
        )

        create_only = dict(base)
        create_only[MODULE_TASKS] = {
            'view': True,
            'create': True,
            'update': False,
            'delete': False,
            'export': False,
        }
        self.group_create = PermissionGroup.objects.create(
            slug='test-tasks-create',
            name='Tasks create only',
            module_permissions=create_only,
        )

        update_only = dict(base)
        update_only[MODULE_TASKS] = {
            'view': True,
            'create': False,
            'update': True,
            'delete': False,
            'export': False,
        }
        self.group_update = PermissionGroup.objects.create(
            slug='test-tasks-update',
            name='Tasks update only',
            module_permissions=update_only,
        )

        delete_only = dict(base)
        delete_only[MODULE_TASKS] = {
            'view': True,
            'create': False,
            'update': False,
            'delete': True,
            'export': False,
        }
        self.group_delete = PermissionGroup.objects.create(
            slug='test-tasks-delete',
            name='Tasks delete only',
            module_permissions=delete_only,
        )

        self.view_user = self._user('tasks_view', ROLE_EMPLOYEE, self.group_view)
        self.leader_create = self._user('tasks_leader_create', ROLE_TEAM_LEADER, self.group_create)
        self.employee = self._user('tasks_employee', ROLE_EMPLOYEE, self.group_view)
        self.leader_create.profile.subordinates.set([self.employee])

        self.director_update = self._user('tasks_dir_update', ROLE_DIRECTOR, self.group_update)
        self.director_delete = self._user('tasks_dir_delete', ROLE_DIRECTOR, self.group_delete)

        self.client = Client(HTTP_HOST='testserver')

    def _user(self, username, role, group):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=role,
            permission_group=group,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_view_only_can_open_my_tasks(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('tasks:my'))
        self.assertEqual(response.status_code, 200)

    def test_view_only_cannot_open_assign(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('tasks:assign'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_view_only_cannot_open_project_create(self):
        self.client.force_login(self.view_user)
        response = self.client.get(reverse('tasks:project_create'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_create_leader_can_open_assign(self):
        self.client.force_login(self.leader_create)
        response = self.client.get(reverse('tasks:assign'))
        self.assertEqual(response.status_code, 200)

    def test_update_only_cannot_open_assign(self):
        self.client.force_login(self.director_update)
        response = self.client.get(reverse('tasks:assign'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('home_portal'))

    def test_create_only_leader_cannot_approve_submitted_task(self):
        task = WorkTask.objects.create(
            title='Chờ duyệt',
            assigner=self.leader_create,
            assignee=self.employee,
            status=WorkTask.STATUS_PENDING_REVIEW,
        )
        self.client.force_login(self.leader_create)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'approve',
            'review_note': 'OK',
        })
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_PENDING_REVIEW)

    def test_update_only_assigner_can_approve_submitted_task(self):
        task = WorkTask.objects.create(
            title='Duyệt được',
            assigner=self.director_update,
            assignee=self.employee,
            status=WorkTask.STATUS_PENDING_REVIEW,
        )
        self.client.force_login(self.director_update)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'approve',
            'review_note': 'Đạt',
        })
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_COMPLETED)

    def test_delete_only_assigner_can_cancel_task(self):
        task = WorkTask.objects.create(
            title='Sẽ hủy',
            assigner=self.director_delete,
            assignee=self.employee,
            status=WorkTask.STATUS_IN_PROGRESS,
        )
        self.client.force_login(self.director_delete)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {'action': 'cancel'})
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_CANCELLED)

    def test_update_only_cannot_cancel_task(self):
        task = WorkTask.objects.create(
            title='Không hủy',
            assigner=self.director_update,
            assignee=self.employee,
            status=WorkTask.STATUS_IN_PROGRESS,
        )
        self.client.force_login(self.director_update)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {'action': 'cancel'})
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_IN_PROGRESS)

    def test_recurrence_pause_requires_update(self):
        recurrence = WorkTaskRecurrence.objects.create(
            assigner=self.leader_create,
            assignee=self.employee,
            title='Lặp tuần',
            frequency=WorkTaskRecurrence.FREQ_WEEKLY,
            interval=1,
            weekday=0,
            start_date=date(2026, 6, 1),
            next_run_date=date(2026, 6, 1),
        )
        self.client.force_login(self.leader_create)
        self.client.post(reverse('tasks:recurrence_action', args=[recurrence.pk]), {'action': 'pause'})
        recurrence.refresh_from_db()
        self.assertTrue(recurrence.is_active)

    def test_recurrence_cancel_requires_delete(self):
        recurrence = WorkTaskRecurrence.objects.create(
            assigner=self.director_update,
            assignee=self.employee,
            title='Lặp tháng',
            frequency=WorkTaskRecurrence.FREQ_MONTHLY,
            interval=1,
            day_of_month=1,
            start_date=date(2026, 6, 1),
            next_run_date=date(2026, 6, 1),
        )
        self.client.force_login(self.director_update)
        self.client.post(reverse('tasks:recurrence_action', args=[recurrence.pk]), {'action': 'cancel'})
        recurrence.refresh_from_db()
        self.assertIsNone(recurrence.end_date)

        owned_by_deleter = WorkTaskRecurrence.objects.create(
            assigner=self.director_delete,
            assignee=self.employee,
            title='Lặp cần dừng',
            frequency=WorkTaskRecurrence.FREQ_MONTHLY,
            interval=1,
            day_of_month=1,
            start_date=date(2026, 6, 1),
            next_run_date=date(2026, 6, 1),
        )
        self.client.force_login(self.director_delete)
        self.client.post(reverse('tasks:recurrence_action', args=[owned_by_deleter.pk]), {'action': 'cancel'})
        owned_by_deleter.refresh_from_db()
        self.assertIsNotNone(owned_by_deleter.end_date)
