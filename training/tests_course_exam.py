from datetime import timedelta

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from assessment.models import Exam
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from training.models import Course, CourseCategory, Enrollment


class CourseExamGateTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Đào tạo', sort_order=1)
        DepartmentMenuPermission.objects.create(
            department=dept,
            modules=['training', 'assessment'],
        )
        RoleModulePermission.objects.update_or_create(
            role=ROLE_EMPLOYEE,
            defaults={
                'module_permissions': {
                    'training': {'view': True, 'edit': False},
                    'assessment': {'view': True, 'edit': False},
                },
            },
        )
        self.user = User.objects.create_user(username='hoc_vien', password='test')
        Profile.objects.filter(user=self.user).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='Học viên',
            is_employed=True,
        )
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

        now = timezone.now()
        self.exam = Exam.objects.create(
            title='Thi cuối khóa',
            start_time=now - timedelta(days=1),
            end_time=now + timedelta(days=1),
            duration_minutes=30,
            is_active=True,
        )
        self.exam.assigned_users.add(self.user)

        category = CourseCategory.objects.create(name='Onboarding')
        self.course = Course.objects.create(
            category=category,
            title='Khóa an toàn',
            description='Nội dung',
            final_exam=self.exam,
            is_active=True,
        )
        self.course.assigned_users.add(self.user)

    def test_take_exam_shows_course_gate_modal_when_incomplete(self):
        Enrollment.objects.get_or_create(user=self.user, course=self.course)

        resp = self.client.get(reverse('take_exam', args=[self.exam.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'courseExamGateModal')
        self.assertContains(resp, 'Bắt đầu học')
        self.assertContains(resp, self.course.title)
        self.assertContains(resp, self.exam.title)
        self.assertContains(resp, reverse('course_start', args=[self.course.pk]))

    def test_take_exam_allowed_when_course_completed(self):
        Enrollment.objects.create(
            user=self.user,
            course=self.course,
            is_completed=True,
            completed_at=timezone.now(),
        )

        resp = self.client.get(reverse('take_exam', args=[self.exam.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_standalone_exam_without_course_link_is_allowed(self):
        standalone = Exam.objects.create(
            title='Thi độc lập',
            start_time=timezone.now() - timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1),
            duration_minutes=20,
            is_active=True,
        )
        standalone.assigned_users.add(self.user)

        resp = self.client.get(reverse('take_exam', args=[standalone.pk]))
        self.assertEqual(resp.status_code, 200)
