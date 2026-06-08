from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from assessment.models import Exam, ExamSubmission
from assessment.portal_widgets import get_portal_dashboard
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE
from training.models import Course, CourseCategory, Enrollment


class PortalTrainingExamWidgetTests(TestCase):
    def setUp(self):
        dept = Department.objects.create(name='Phòng ĐT', sort_order=1)
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

        self.employee = User.objects.create_user(username='nv_dt', password='testpass123')
        Profile.objects.filter(user=self.employee).update(
            department=dept,
            role=ROLE_EMPLOYEE,
            full_name='NV ĐT',
            is_employed=True,
        )
        self.employee.refresh_from_db()

        self.category = CourseCategory.objects.create(name='Onboarding')

    def _create_course(self, title='Khóa test'):
        course = Course.objects.create(
            category=self.category,
            title=title,
            description='Mô tả',
            is_active=True,
        )
        course.assigned_users.add(self.employee)
        return course

    def _create_exam(self, title='Bài thi test', *, start_delta=-1, end_delta=1):
        now = timezone.now()
        exam = Exam.objects.create(
            title=title,
            start_time=now + timedelta(days=start_delta),
            end_time=now + timedelta(days=end_delta),
            duration_minutes=30,
            is_active=True,
        )
        exam.assigned_users.add(self.employee)
        return exam

    def test_assigned_course_shows_on_home_widget(self):
        self._create_course()
        widgets = get_portal_dashboard(self.employee)
        titles = [w['title'] for w in widgets]
        self.assertIn('Khóa học chưa hoàn thành', titles)

    def test_completed_course_not_on_home_widget(self):
        course = self._create_course()
        Enrollment.objects.create(user=self.employee, course=course, is_completed=True)
        widgets = get_portal_dashboard(self.employee)
        titles = [w['title'] for w in widgets]
        self.assertNotIn('Khóa học chưa hoàn thành', titles)

    def test_assigned_exam_shows_even_before_start(self):
        self._create_exam(start_delta=1, end_delta=3)
        widgets = get_portal_dashboard(self.employee)
        match = [w for w in widgets if w['title'] == 'Bài kiểm tra']
        self.assertEqual(len(match), 1)
        self.assertIn('sắp mở', match[0]['text'])

    def test_assigned_exam_shows_after_end_if_not_submitted(self):
        self._create_exam(start_delta=-5, end_delta=-1)
        widgets = get_portal_dashboard(self.employee)
        match = [w for w in widgets if w['title'] == 'Bài kiểm tra']
        self.assertEqual(len(match), 1)
        self.assertIn('quá hạn', match[0]['text'])

    def test_submitted_exam_not_on_home_widget(self):
        exam = self._create_exam()
        ExamSubmission.objects.create(
            user=self.employee,
            exam=exam,
            submitted_at=timezone.now(),
            is_completed=True,
        )
        widgets = get_portal_dashboard(self.employee)
        titles = [w['title'] for w in widgets]
        self.assertNotIn('Bài kiểm tra', titles)


class PaginationHelperTests(TestCase):
    def test_pagination_link_items_compact_range(self):
        from PortalJustPlay.pagination import pagination_link_items

        class _Page:
            def __init__(self, number, num_pages):
                self.number = number
                self.paginator = type('P', (), {'num_pages': num_pages})()

        self.assertEqual(pagination_link_items(_Page(1, 5)), [1, 2, 3, 4, 5])
        self.assertEqual(
            pagination_link_items(_Page(5, 10)),
            [1, None, 3, 4, 5, 6, 7, None, 10],
        )

    def test_pagination_href(self):
        from PortalJustPlay.pagination import pagination_href

        self.assertEqual(pagination_href('q=abc', 'page', 3), '?q=abc&page=3')
        self.assertEqual(pagination_href('', 'page', 2), '?page=2')
        self.assertEqual(pagination_href('sort=name', 'my_page', 4), '?sort=name&my_page=4')
