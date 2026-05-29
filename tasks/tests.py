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
    can_create_internal_project,
    can_view_project,
    can_view_task,
    format_team_user_label,
)
from tasks.models import InternalProject, ProjectComment, WorkTask, WorkTaskAttachment, WorkTaskHandoff


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

    def test_assign_with_separate_image_and_file(self):
        self.client.force_login(self.leader)
        image = SimpleUploadedFile('ref.jpg', b'fake-image-bytes', content_type='image/jpeg')
        doc = SimpleUploadedFile('spec.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = self.client.post(reverse('tasks:assign'), {
            'title': 'Việc có ảnh và file',
            'description': '',
            'task_type': WorkTask.TYPE_GENERAL,
            'priority': WorkTask.PRIORITY_NORMAL,
            'assignees': [self.employee.pk],
            'images': image,
            'files': doc,
        })
        self.assertEqual(response.status_code, 302)
        task = WorkTask.objects.get(assigner=self.leader, title='Việc có ảnh và file')
        self.assertEqual(task.attachments.filter(stage=WorkTaskAttachment.STAGE_ASSIGN).count(), 2)

    def test_assignee_upload_work_attachment(self):
        task = WorkTask.objects.create(
            title='Upload kết quả',
            assigner=self.leader,
            assignee=self.employee,
            status=WorkTask.STATUS_IN_PROGRESS,
        )
        self.client.force_login(self.employee)
        image = SimpleUploadedFile('proof.png', b'png-bytes', content_type='image/png')
        doc = SimpleUploadedFile('done.pdf', b'%PDF-1.4', content_type='application/pdf')
        response = self.client.post(reverse('tasks:detail', args=[task.pk]), {
            'action': 'upload_attachment',
            'images': image,
            'files': doc,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(task.attachments.filter(stage=WorkTaskAttachment.STAGE_WORK).count(), 2)

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

    def test_assign_single_person_end_to_end(self):
        """Giao 1 người: form → 1 bản ghi → redirect chi tiết → NV thấy & xác nhận."""
        self.client.force_login(self.leader)

        response = self.client.get(reverse('tasks:assign'))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('tasks:assign'), {
            'title': 'Việc test 1 người',
            'description': 'Mô tả test',
            'task_type': WorkTask.TYPE_GENERAL,
            'priority': WorkTask.PRIORITY_HIGH,
            'due_date': '2026-06-01',
            'assignees': [self.employee.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(WorkTask.objects.filter(assigner=self.leader, title='Việc test 1 người').count(), 1)

        task = WorkTask.objects.get(title='Việc test 1 người')
        self.assertEqual(task.assignee, self.employee)
        self.assertEqual(task.status, WorkTask.STATUS_PENDING_ACK)
        self.assertEqual(task.priority, WorkTask.PRIORITY_HIGH)
        self.assertRedirects(response, reverse('tasks:detail', args=[task.pk]))

        response = self.client.get(reverse('tasks:detail', args=[task.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Việc test 1 người')

        self.client.force_login(self.employee)
        response = self.client.get(reverse('tasks:my'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Việc test 1 người')

        response = self.client.post(reverse('tasks:detail', args=[task.pk]), {'action': 'acknowledge'})
        self.assertEqual(response.status_code, 302)
        task.refresh_from_db()
        self.assertEqual(task.status, WorkTask.STATUS_IN_PROGRESS)

    def test_outsider_cannot_view_task(self):
        task = WorkTask.objects.create(
            title='Private',
            assigner=self.leader,
            assignee=self.employee,
        )
        self.assertTrue(can_view_task(self.employee, task))
        self.assertTrue(can_view_task(self.leader, task))
        self.assertFalse(can_view_task(self.other, task))


class InternalProjectTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Xưởng DA', sort_order=1)
        DepartmentMenuPermission.objects.create(department=dept, modules=['tasks'])
        task_perms = {'tasks': {'view': True, 'edit': True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': task_perms},
            )

        self.employee = self._user('nv_da', ROLE_EMPLOYEE, dept)
        self.other = self._user('nv_da2', ROLE_EMPLOYEE, dept)
        self.leader = self._user('tt_da', ROLE_TEAM_LEADER, dept)
        self.leader.profile.subordinates.set([self.employee, self.other])
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

    def test_leader_can_create_project(self):
        self.assertTrue(can_create_internal_project(self.leader))
        self.assertFalse(can_create_internal_project(self.employee))

    def test_create_project_with_members_and_steps(self):
        self.client.force_login(self.leader)
        response = self.client.post(reverse('tasks:project_create'), {
            'title': 'Dự án test',
            'description': 'Mô tả',
            'due_date': '2026-07-01',
            'members': [self.employee.pk, self.other.pk],
        })
        self.assertEqual(response.status_code, 302)
        project = InternalProject.objects.get(title='Dự án test')
        self.assertEqual(project.owner, self.leader)
        self.assertEqual(project.members.count(), 2)

        response = self.client.post(reverse('tasks:project_detail', args=[project.pk]), {
            'action': 'add_step',
            'title': 'Bước 1',
            'description': '',
            'assignee': self.employee.pk,
            'priority': WorkTask.PRIORITY_NORMAL,
        })
        self.assertEqual(response.status_code, 302)
        step = project.steps.get(title='Bước 1')
        self.assertEqual(step.status, WorkTask.STATUS_PENDING_ACK)
        self.assertEqual(step.assigner, self.leader)

    def test_dependent_step_blocked_until_prerequisite_done(self):
        project = InternalProject.objects.create(
            title='Phụ thuộc',
            owner=self.leader,
        )
        project.members.set([self.employee, self.other])
        step1 = WorkTask.objects.create(
            title='Bước A',
            assigner=self.leader,
            assignee=self.employee,
            project=project,
            step_order=1,
            status=WorkTask.STATUS_PENDING_ACK,
        )
        step2 = WorkTask.objects.create(
            title='Bước B',
            assigner=self.leader,
            assignee=self.other,
            project=project,
            step_order=2,
            depends_on=step1,
            status=WorkTask.STATUS_BLOCKED,
        )
        self.assertEqual(step2.status, WorkTask.STATUS_BLOCKED)

        step1.status = WorkTask.STATUS_COMPLETED
        step1.save()
        from tasks.project_utils import unlock_dependent_steps
        unlocked = unlock_dependent_steps(step1)
        step2.refresh_from_db()
        self.assertEqual(len(unlocked), 1)
        self.assertEqual(step2.status, WorkTask.STATUS_PENDING_ACK)

    def test_member_can_view_project_and_comment(self):
        project = InternalProject.objects.create(title='Comment test', owner=self.leader)
        project.members.set([self.employee])
        self.assertTrue(can_view_project(self.employee, project))

        self.client.force_login(self.employee)
        response = self.client.get(reverse('tasks:project_detail', args=[project.pk]))
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('tasks:project_detail', args=[project.pk]), {
            'action': 'comment',
            'body': 'Cập nhật @nv_da tiến độ OK',
        })
        self.assertEqual(response.status_code, 302)
        comment = ProjectComment.objects.get(project=project)
        self.assertIn(self.employee, comment.mentioned_users.all())

    def test_handoff_request_and_owner_approval(self):
        project = InternalProject.objects.create(title='Handoff', owner=self.leader)
        project.members.set([self.employee, self.other])
        task = WorkTask.objects.create(
            title='Bước handoff',
            assigner=self.leader,
            assignee=self.employee,
            project=project,
            status=WorkTask.STATUS_IN_PROGRESS,
        )

        self.client.force_login(self.employee)
        response = self.client.post(reverse('tasks:handoff', args=[task.pk]), {
            'to_user': self.other.pk,
            'note': 'Nghỉ phép',
        })
        self.assertEqual(response.status_code, 302)
        handoff = WorkTaskHandoff.objects.get(source_task=task)
        self.assertEqual(handoff.status, WorkTaskHandoff.STATUS_PENDING)

        self.client.force_login(self.leader)
        response = self.client.post(reverse('tasks:project_detail', args=[project.pk]), {
            'action': 'approve_handoff',
            'handoff_id': handoff.pk,
        })
        self.assertEqual(response.status_code, 302)
        handoff.refresh_from_db()
        task.refresh_from_db()
        self.assertEqual(handoff.status, WorkTaskHandoff.STATUS_APPROVED)
        self.assertEqual(task.status, WorkTask.STATUS_HANDED_OFF)
        self.assertIsNotNone(handoff.created_task)
        self.assertEqual(handoff.created_task.assignee, self.other)

    def test_project_member_can_view_teammate_step(self):
        project = InternalProject.objects.create(title='Team view', owner=self.leader)
        project.members.set([self.employee, self.other])
        task = WorkTask.objects.create(
            title='Bước của người khác',
            assigner=self.leader,
            assignee=self.other,
            project=project,
        )
        self.assertTrue(can_view_task(self.employee, task))
        self.client.force_login(self.employee)
        response = self.client.get(reverse('tasks:detail', args=[task.pk]))
        self.assertEqual(response.status_code, 200)
