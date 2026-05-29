import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
    can_assign_tasks,
    can_view_task,
    format_team_user_label,
)
from tasks.models import WorkTask, WorkTaskAttachment


class TaskWorkflowTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Xưởng CV', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['tasks'])

        task_perms = {
            'tasks': {'view': True, 'edit': True},
        }
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': task_perms},
            )

        self.employee = self._user('nv_cv', ROLE_EMPLOYEE, dept)
        self.leader = self._user('leader_cv', ROLE_TEAM_LEADER, dept)
        self.director = self._user('gd_cv', ROLE_DIRECTOR, dept)
        self.other = self._user('nv_khac', ROLE_EMPLOYEE, dept)

        self.leader.profile.subordinates.set([self.employee])
        self.director.profile.subordinates.set([self.leader])

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

    def test_director_can_assign_with_subordinates(self):
        self.assertTrue(can_assign_tasks(self.director))
        self.assertFalse(can_assign_tasks(self.employee))

    def test_assign_creates_one_record_per_assignee(self):
        self.client.force_login(self.leader)
        batch = uuid.uuid4()
        response = self.client.post(reverse('tasks:assign'), {
            'title': 'Việc chung',
            'description': 'Mô tả',
            'task_type': WorkTask.TYPE_GENERAL,
            'priority': WorkTask.PRIORITY_NORMAL,
            'assignees': [self.employee.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkTask.objects.filter(assigner=self.leader).count(), 1)
        task = WorkTask.objects.get(assigner=self.leader)
        self.assertEqual(task.assignee, self.employee)
        self.assertEqual(task.status, WorkTask.STATUS_PENDING_ACK)

    def test_full_workflow_ack_submit_approve(self):
        task = WorkTask.objects.create(
            title='Test flow',
            assigner=self.leader,
            assignee=self.employee,
        )

        self.client.force_login(self.employee)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {'action': 'acknowledge'})
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_IN_PROGRESS)

        self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'submit',
            'result_note': 'Xong rồi',
        })
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_PENDING_REVIEW)

        self.client.force_login(self.leader)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'approve',
            'review_note': 'OK',
        })
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_COMPLETED)

    def test_reject_and_reassign(self):
        self.leader.profile.subordinates.add(self.other)
        task = WorkTask.objects.create(
            title='Việc bị từ chối',
            assigner=self.leader,
            assignee=self.employee,
        )
        self.client.force_login(self.employee)
        self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'reject',
            'reject_reason': 'Không kịp',
        })
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_REJECTED)

        self.client.force_login(self.leader)
        response = self.client.post(reverse('tasks:reassign', args=[task.pk]), {
            'assignee': self.other.pk,
        })
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_REASSIGNED)
        new_task = WorkTask.objects.get(reassigned_from=task)
        self.assertEqual(new_task.assignee, self.other)
        self.assertEqual(new_task.status, WorkTask.STATUS_PENDING_ACK)

    def test_my_tasks_page_renders(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('tasks:my'))
        self.assertEqual(response.status_code, 200)

    def test_assigned_page_renders(self):
        self.client.force_login(self.leader)
        response = self.client.get(reverse('tasks:assigned'))
        self.assertEqual(response.status_code, 200)

    def test_assign_with_attachment(self):
        self.client.force_login(self.leader)
        image = SimpleUploadedFile('ref.jpg', b'fake-image-bytes', content_type='image/jpeg')
        response = self.client.post(reverse('tasks:assign'), {
            'title': 'Việc có ảnh',
            'description': '',
            'task_type': WorkTask.TYPE_GENERAL,
            'priority': WorkTask.PRIORITY_NORMAL,
            'assignees': [self.employee.pk],
            'attachments': image,
        })
        self.assertEqual(response.status_code, 302)
        task = WorkTask.objects.get(assigner=self.leader, title='Việc có ảnh')
        self.assertEqual(task.attachments.filter(stage=WorkTaskAttachment.STAGE_ASSIGN).count(), 1)

    def test_assignee_upload_work_attachment(self):
        task = WorkTask.objects.create(
            title='Upload kết quả',
            assigner=self.leader,
            assignee=self.employee,
            status=WorkTask.STATUS_IN_PROGRESS,
        )
        self.client.force_login(self.employee)
        file = SimpleUploadedFile('done.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'upload_attachment',
            'attachments': file,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.attachments.filter(stage=WorkTaskAttachment.STAGE_WORK).count(), 1)

    def test_assignee_label_shows_name_code_account(self):
        Profile.objects.filter(user=self.employee).update(
            full_name='Nguyễn Văn A',
            employee_code='NV001',
        )
        self.employee.refresh_from_db()
        label = format_team_user_label(self.employee)
        self.assertIn('Nguyễn Văn A', label)
        self.assertIn('NV001', label)
        self.assertIn('nv_cv', label)

    def test_outsider_cannot_view_task(self):
        task = WorkTask.objects.create(
            title='Private',
            assigner=self.leader,
            assignee=self.employee,
        )
        self.assertTrue(can_view_task(self.employee, task))
        self.assertTrue(can_view_task(self.leader, task))
        self.assertFalse(can_view_task(self.other, task))
