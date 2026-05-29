from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from assessment.portal_widgets import get_portal_dashboard
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_DIVISION_HEAD, ROLE_EMPLOYEE
from service_requests.models import RequestType, RequestTypeStepTemplate, ServiceRequest, ServiceRequestStep
from service_requests.workflow import approve_step, complete_execution_step, create_request_with_steps, get_active_request_type


class ServiceRequestWorkflowTests(TestCase):
    def setUp(self):
        self.dept_prod = Department.objects.create(name='Sản xuất', sort_order=1)
        self.dept_accounting = Department.objects.create(name='Kế toán', sort_order=2)
        self.dept_procurement = Department.objects.create(name='Thu mua', sort_order=3)

        DepartmentMenuPermission.objects.create(
            department=self.dept_prod,
            modules=['service_requests', 'tasks'],
        )
        DepartmentMenuPermission.objects.create(
            department=self.dept_accounting,
            modules=['service_requests'],
        )
        DepartmentMenuPermission.objects.create(
            department=self.dept_procurement,
            modules=['service_requests'],
        )

        perms = {
            'service_requests': {'view': True, 'edit': True},
            'tasks': {'view': True, 'edit': True},
        }
        for role in (ROLE_EMPLOYEE, ROLE_DIVISION_HEAD):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.div_head = self._user('tbp_test', ROLE_DIVISION_HEAD, self.dept_prod)
        self.employee = self._user('nv_test', ROLE_EMPLOYEE, self.dept_prod)
        self.accountant = self._user('kt_test', ROLE_EMPLOYEE, self.dept_accounting)
        self.buyer = self._user('tm_test', ROLE_EMPLOYEE, self.dept_procurement)

        self.div_head.profile.subordinates.set([self.employee])

        self.request_type, _ = RequestType.objects.get_or_create(
            code=RequestType.CODE_ASSET_PURCHASE,
            defaults={
                'name': 'Đề xuất mua tài sản',
                'is_active': True,
            },
        )
        self.request_type.step_templates.all().delete()
        RequestTypeStepTemplate.objects.create(
            request_type=self.request_type,
            step_order=1,
            name='Trưởng bộ phận duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
        )
        RequestTypeStepTemplate.objects.create(
            request_type=self.request_type,
            step_order=2,
            name='Kế toán duyệt chi phí',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department=self.dept_accounting,
        )
        RequestTypeStepTemplate.objects.create(
            request_type=self.request_type,
            step_order=3,
            name='Thu mua thực hiện',
            step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department=self.dept_procurement,
        )

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

    def test_create_request_assigns_division_head_first(self):
        req = create_request_with_steps(
            requester=self.employee,
            request_type=self.request_type,
            title='Mua laptop',
            description='Cần laptop dev',
            estimated_cost=15000000,
        )
        step1 = req.steps.get(step_order=1)
        self.assertEqual(step1.assignee, self.div_head)
        self.assertEqual(step1.status, ServiceRequestStep.STATUS_PENDING)
        step2 = req.steps.get(step_order=2)
        self.assertEqual(step2.status, ServiceRequestStep.STATUS_BLOCKED)

    def test_full_asset_workflow(self):
        req = create_request_with_steps(
            requester=self.employee,
            request_type=self.request_type,
            title='Mua laptop',
            description='Cần laptop dev',
        )
        step1 = req.steps.get(step_order=1)
        approve_step(step1, actor=self.div_head, note='Đồng ý')

        req.refresh_from_db()
        step2 = req.steps.get(step_order=2)
        self.assertEqual(step2.status, ServiceRequestStep.STATUS_PENDING)
        self.assertIsNone(step2.assignee_id)

        approve_step(step2, actor=self.accountant, note='Đủ ngân sách')

        step3 = req.steps.get(step_order=3)
        self.assertEqual(step3.status, ServiceRequestStep.STATUS_PENDING)

        complete_execution_step(step3, actor=self.buyer, note='Đã mua Dell Latitude')

        req.refresh_from_db()
        self.assertEqual(req.status, ServiceRequest.STATUS_COMPLETED)

    def test_pending_widget_for_division_head(self):
        create_request_with_steps(
            requester=self.employee,
            request_type=self.request_type,
            title='Mua laptop',
            description='Test',
        )
        widgets = get_portal_dashboard(self.div_head)
        titles = [w['title'] for w in widgets]
        self.assertIn('Yêu cầu chờ xử lý', titles)

    def test_create_page_renders(self):
        self.assertIsNotNone(get_active_request_type())
        self.client.force_login(self.employee)
        response = self.client.get(reverse('service_requests:create'))
        self.assertEqual(response.status_code, 200)

    def test_employee_sees_my_requests_after_submit(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse('service_requests:create'), {
            'title': 'Mua máy in',
            'description': 'Cần máy in A4',
            'estimated_cost': '5000000',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ServiceRequest.objects.filter(requester=self.employee).count(), 1)
