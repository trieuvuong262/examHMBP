from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_DIRECTOR, ROLE_DIVISION_HEAD, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from tasks.models import InternalProject, WorkTask


class CrossDeptProjectTests(TestCase):
    def setUp(self):
        self.dept_a = Department.objects.create(name='Phong SX', sort_order=1)
        self.dept_b = Department.objects.create(name='Phong KT', sort_order=2)
        self.dept_c = Department.objects.create(name='Phong HC', sort_order=3)
        for dept in (self.dept_a, self.dept_b, self.dept_c):
            DepartmentMenuPermission.objects.create(department=dept, modules=['tasks'])

        task_perms = {'tasks': {'view': True, 'edit': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': task_perms},
            )

        self.leader_a = self._user('tp_sx', ROLE_TEAM_LEADER, self.dept_a)
        self.leader_b = self._user('tp_kt', ROLE_TEAM_LEADER, self.dept_b)
        self.employee_a = self._user('nv_sx', ROLE_EMPLOYEE, self.dept_a)
        self.employee_b = self._user('nv_kt', ROLE_EMPLOYEE, self.dept_b)
        self.director = self._user('gd_lp', ROLE_DIRECTOR, self.dept_a)
        self.div_head = self._user('tbp_x', ROLE_DIVISION_HEAD, self.dept_a)
        self.client = Client()

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=dept,
            role=role,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_director_and_team_leader_can_create_cross_dept(self):
        from hrm.permissions import can_create_cross_dept_project

        self.assertTrue(can_create_cross_dept_project(self.director))
        self.assertTrue(can_create_cross_dept_project(self.leader_a))
        self.assertFalse(can_create_cross_dept_project(self.div_head))
        self.assertFalse(can_create_cross_dept_project(self.employee_a))

    def test_create_cross_dept_project_requires_two_departments(self):
        self.client.force_login(self.director)
        response = self.client.post(reverse('tasks:cross_dept_create'), {
            'title': 'DA LPB',
            'description': 'Test',
            'departments': [self.dept_a.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(InternalProject.objects.filter(title='DA LPB').exists())

        response = self.client.post(reverse('tasks:cross_dept_create'), {
            'title': 'DA LPB',
            'description': 'Test',
            'departments': [self.dept_a.pk, self.dept_b.pk],
        })
        self.assertEqual(response.status_code, 302)
        project = InternalProject.objects.get(title='DA LPB')
        self.assertEqual(project.project_type, InternalProject.TYPE_CROSS_DEPT)
        self.assertEqual(project.departments.count(), 2)

    def test_dept_queue_step_claim_flow(self):
        self.client.force_login(self.director)
        self.client.post(reverse('tasks:cross_dept_create'), {
            'title': 'Du an claim',
            'description': '',
            'departments': [self.dept_a.pk, self.dept_b.pk],
        })
        project = InternalProject.objects.get(title='Du an claim')

        response = self.client.post(reverse('tasks:cross_dept_detail', args=[project.pk]), {
            'action': 'add_step',
            'title': 'Buoc KT',
            'description': '',
            'target_department': self.dept_b.pk,
            'assignee_mode': WorkTask.ASSIGNEE_DEPT_QUEUE,
            'priority': WorkTask.PRIORITY_NORMAL,
        })
        self.assertEqual(response.status_code, 302)
        step = project.steps.get(title='Buoc KT')
        self.assertEqual(step.status, WorkTask.STATUS_PENDING_CLAIM)
        self.assertIsNone(step.assignee_id)

        self.client.force_login(self.employee_b)
        response = self.client.post(reverse('tasks:cross_dept_claim', args=[step.pk]))
        self.assertEqual(response.status_code, 302)
        step.refresh_from_db()
        self.assertEqual(step.assignee, self.employee_b)
        self.assertEqual(step.status, WorkTask.STATUS_PENDING_ACK)
        self.assertTrue(project.members.filter(pk=self.employee_b.pk).exists())

    def test_dept_head_read_only_view(self):
        from hrm.permissions import can_manage_project, can_view_project, is_cross_dept_read_only_viewer

        project = InternalProject.objects.create(
            title='Read only',
            owner=self.director,
            project_type=InternalProject.TYPE_CROSS_DEPT,
        )
        project.departments.set([self.dept_a, self.dept_b])

        self.assertTrue(can_view_project(self.leader_a, project))
        self.assertTrue(is_cross_dept_read_only_viewer(self.leader_a, project))
        self.assertFalse(can_manage_project(self.leader_a, project))
        self.assertFalse(can_view_project(self.employee_a, project))

        self.client.force_login(self.leader_a)
        response = self.client.get(reverse('tasks:cross_dept_detail', args=[project.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'chỉ đọc')

    def test_team_projects_excluded_from_internal_list(self):
        InternalProject.objects.create(
            title='Noi bo',
            owner=self.director,
            project_type=InternalProject.TYPE_TEAM,
        )
        InternalProject.objects.create(
            title='Lien phong',
            owner=self.director,
            project_type=InternalProject.TYPE_CROSS_DEPT,
        )
        project = InternalProject.objects.get(title='Lien phong')
        project.departments.set([self.dept_a, self.dept_b])

        self.client.force_login(self.director)
        response = self.client.get(reverse('tasks:project_list'))
        self.assertContains(response, 'Noi bo')
        self.assertNotContains(response, 'Lien phong')

        response = self.client.get(reverse('tasks:cross_dept_list'))
        self.assertContains(response, 'Lien phong')
        self.assertNotContains(response, 'Noi bo')

    def test_dependent_queue_unlocks_to_pending_claim(self):
        project = InternalProject.objects.create(
            title='Unlock queue',
            owner=self.director,
            project_type=InternalProject.TYPE_CROSS_DEPT,
        )
        project.departments.set([self.dept_a, self.dept_b])
        step1 = WorkTask.objects.create(
            title='Buoc 1',
            assigner=self.director,
            assignee=self.employee_a,
            project=project,
            target_department=self.dept_a,
            assignee_mode=WorkTask.ASSIGNEE_SPECIFIC,
            step_order=1,
            status=WorkTask.STATUS_IN_PROGRESS,
        )
        step2 = WorkTask.objects.create(
            title='Buoc 2',
            assigner=self.director,
            assignee=None,
            project=project,
            target_department=self.dept_b,
            assignee_mode=WorkTask.ASSIGNEE_DEPT_QUEUE,
            depends_on=step1,
            step_order=2,
            status=WorkTask.STATUS_BLOCKED,
        )
        step1.status = WorkTask.STATUS_COMPLETED
        step1.save()
        from tasks.project_utils import unlock_dependent_steps
        unlock_dependent_steps(step1)
        step2.refresh_from_db()
        self.assertEqual(step2.status, WorkTask.STATUS_PENDING_CLAIM)
