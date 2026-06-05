from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from assessment.portal_widgets import get_portal_dashboard
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_DIRECTOR, ROLE_DIVISION_HEAD, ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from service_requests.models import (
    RecurringItemCatalog,
    RequestType,
    ServiceRequest,
    ServiceRequestStep,
)
from service_requests.permissions import can_manage_recurring_catalog, can_view_pricing
from service_requests.workflow import (
    AMOUNT_ACCOUNTING_MIN,
    AMOUNT_DIRECTOR_MIN,
    approve_step,
    complete_execution_step,
    complete_procurement_quote,
    complete_purchase_step,
    create_request_with_steps,
    get_active_request_type,
)


class ServiceRequestWorkflowTests(TestCase):
    def setUp(self):
        self.dept_hr = Department.objects.create(name='HCNS', sort_order=0)
        self.dept_prod = Department.objects.create(name='Sản xuất', sort_order=1)
        self.dept_accounting = Department.objects.create(name='Kế toán', sort_order=2)
        self.dept_procurement = Department.objects.create(name='Thu mua', sort_order=3)

        for dept in (self.dept_hr, self.dept_prod, self.dept_accounting, self.dept_procurement):
            DepartmentMenuPermission.objects.create(
                department=dept,
                modules=['de_xuat', 'ho_tro', 'tasks'],
            )

        perms = {
            'de_xuat': {'view': True, 'edit': True},
            'ho_tro': {'view': True, 'edit': True},
            'tasks': {'view': True, 'edit': True},
        }
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.team_leader = self._user('tt_test', ROLE_TEAM_LEADER, self.dept_prod)
        self.div_head = self._user('tbp_test', ROLE_DIVISION_HEAD, self.dept_prod)
        self.employee = self._user('nv_test', ROLE_EMPLOYEE, self.dept_prod)
        self.employee_hr = self._user('nv_hr', ROLE_EMPLOYEE, self.dept_hr)
        self.accountant = self._user('kt_test', ROLE_EMPLOYEE, self.dept_accounting)
        self.buyer = self._user('tm_test', ROLE_EMPLOYEE, self.dept_procurement)
        self.director = self._user('gd_test', ROLE_DIRECTOR, self.dept_prod)

        self.team_leader.profile.subordinates.set([self.employee])
        self.div_head.profile.subordinates.set([self.employee, self.team_leader])

        self.request_type, _ = RequestType.objects.get_or_create(
            code=RequestType.CODE_ASSET_PURCHASE,
            defaults={'name': 'Đề xuất mua tài sản', 'is_active': True},
        )

        self.catalog_item = RecurringItemCatalog.objects.create(
            name='Giấy A4',
            unit='ram',
            is_active=True,
            created_by=self.buyer,
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

    def _create_request(self, **kwargs):
        defaults = {
            'requester': self.employee,
            'request_type': self.request_type,
            'title': 'Mua vật tư',
            'description': 'Cần mua vật tư sản xuất',
            'line_items': [{'description': 'Keo dán', 'quantity': Decimal('10'), 'unit': 'chai'}],
        }
        defaults.update(kwargs)
        return create_request_with_steps(**defaults)

    def _submit_quote(self, req, *, unit_price=Decimal('500000'), qty=Decimal('10')):
        step = req.steps.get(step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE)
        line = req.line_items.first()
        complete_procurement_quote(
            step,
            actor=self.buyer,
            line_updates={
                line.pk: {
                    'quantity_confirmed': qty,
                    'quotes': [{
                        'supplier_name': 'NCC A',
                        'unit_price': unit_price,
                        'is_selected': True,
                    }],
                },
            },
            note='Báo giá xong',
        )
        req.refresh_from_db()

    def _approve_division_head(self, req, *, buyer=None):
        buyer = buyer or self.buyer
        approve_step(
            req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD),
            actor=self.div_head,
            procurement_assignee=buyer,
            note='Đồng ý',
        )
        req.refresh_from_db()

    def _approve_through_quote(self, req, *, unit_price=Decimal('100000')):
        if req.steps.filter(step_code=ServiceRequestStep.STEP_TEAM_LEADER).exists():
            approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        if req.steps.filter(step_code=ServiceRequestStep.STEP_DIVISION_HEAD).exists():
            self._approve_division_head(req)
        self._submit_quote(req, unit_price=unit_price)

    # --- Yêu cầu: Tổ trưởng duyệt nếu phòng có Tổ trưởng & người gửi là NV ---

    def test_employee_starts_with_team_leader_when_dept_has_tl(self):
        req = self._create_request()
        step1 = req.steps.order_by('step_order').first()
        self.assertEqual(step1.step_code, ServiceRequestStep.STEP_TEAM_LEADER)
        self.assertEqual(step1.assignee, self.team_leader)

    # --- Yêu cầu: Bỏ qua Tổ trưởng nếu phòng không có Tổ trưởng ---

    def test_dept_without_team_leader_skips_to_division_head(self):
        req = self._create_request(requester=self.employee_hr)
        codes = list(req.steps.values_list('step_code', flat=True))
        self.assertNotIn(ServiceRequestStep.STEP_TEAM_LEADER, codes)
        self.assertEqual(codes[0], ServiceRequestStep.STEP_DIVISION_HEAD)

    def test_director_hidden_division_head_when_no_tbp_in_chain(self):
        """Giám đốc = trưởng BP ẩn — gán duyệt khi NV không có TBP trực tiếp."""
        req = self._create_request(requester=self.employee_hr)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        self.assertEqual(dh.assignee, self.director)

    def test_director_pending_and_handle_division_head(self):
        from service_requests.permissions import can_handle_step, pending_steps_for_user

        req = self._create_request(requester=self.employee_hr)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        self.assertTrue(can_handle_step(self.director, dh))
        self.assertTrue(pending_steps_for_user(self.director).filter(pk=dh.pk).exists())

    def test_director_handles_division_head_when_tbp_already_assigned(self):
        from hrm.permissions import is_division_head
        from service_requests.permissions import can_handle_step, pending_steps_for_user

        self.assertTrue(is_division_head(self.director))
        req = self._create_request()
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        dh.assignee = self.div_head
        dh.save(update_fields=['assignee'])
        self.assertTrue(can_handle_step(self.director, dh))
        self.assertTrue(pending_steps_for_user(self.director).filter(pk=dh.pk).exists())

    # --- Yêu cầu: Trưởng BP gửi → bỏ qua duyệt BP, vẫn qua Thu mua ---

    def test_division_head_proposer_skips_approvals_goes_to_procurement(self):
        req = self._create_request(requester=self.div_head)
        codes = list(req.steps.values_list('step_code', flat=True))
        self.assertNotIn(ServiceRequestStep.STEP_TEAM_LEADER, codes)
        self.assertNotIn(ServiceRequestStep.STEP_DIVISION_HEAD, codes)
        self.assertEqual(codes[0], ServiceRequestStep.STEP_PROCUREMENT_QUOTE)

    # --- Yêu cầu: Tổ trưởng gửi → bỏ qua bước Tổ trưởng, vẫn cần Trưởng BP ---

    def test_team_leader_proposer_skips_tl_needs_division_head(self):
        req = self._create_request(requester=self.team_leader)
        codes = list(req.steps.values_list('step_code', flat=True))
        self.assertNotIn(ServiceRequestStep.STEP_TEAM_LEADER, codes)
        self.assertEqual(codes[0], ServiceRequestStep.STEP_DIVISION_HEAD)

    def test_division_head_assigns_procurement_staff_on_approve(self):
        req = self._create_request()
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        self._approve_division_head(req)
        quote = req.steps.get(step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE)
        self.assertEqual(quote.assignee, self.buyer)
        self.assertEqual(quote.status, ServiceRequestStep.STATUS_IN_PROGRESS)
    # --- Yêu cầu: <2M → không cần KT/GĐ ---

    def test_low_amount_skips_accountant_after_quote(self):
        req = self._create_request()
        self._approve_through_quote(req, unit_price=Decimal('100000'))

        self.assertEqual(req.approval_tier, ServiceRequest.TIER_NONE)
        self.assertFalse(req.steps.filter(step_code=ServiceRequestStep.STEP_ACCOUNTANT).exists())
        self.assertFalse(req.steps.filter(step_code=ServiceRequestStep.STEP_DIRECTOR).exists())

    # --- Yêu cầu: 2M–10M → Kế toán duyệt ---

    def test_mid_amount_requires_accountant(self):
        req = self._create_request()
        price = AMOUNT_ACCOUNTING_MIN / Decimal('10')
        self._approve_through_quote(req, unit_price=price)

        self.assertEqual(req.approval_tier, ServiceRequest.TIER_ACCOUNTANT)
        acct_step = req.steps.get(step_code=ServiceRequestStep.STEP_ACCOUNTANT)
        self.assertEqual(acct_step.status, ServiceRequestStep.STATUS_PENDING)

    # --- Yêu cầu: >10M → Giám đốc duyệt ---

    def test_high_amount_requires_director(self):
        req = self._create_request()
        price = AMOUNT_DIRECTOR_MIN / Decimal('5')
        self._approve_through_quote(req, unit_price=price)

        self.assertEqual(req.approval_tier, ServiceRequest.TIER_DIRECTOR)
        dir_step = req.steps.get(step_code=ServiceRequestStep.STEP_DIRECTOR)
        self.assertEqual(dir_step.status, ServiceRequestStep.STATUS_PENDING)

    # --- Yêu cầu: Hàng định kỳ → bỏ qua KT/GĐ dù giá cao ---

    def test_recurring_catalog_skips_approval_even_high_amount(self):
        req = self._create_request(
            recurring_item=self.catalog_item,
            line_items=None,
        )
        self._approve_through_quote(req, unit_price=AMOUNT_DIRECTOR_MIN)

        self.assertTrue(req.is_from_catalog)
        self.assertEqual(req.approval_tier, ServiceRequest.TIER_NONE)
        self.assertFalse(req.steps.filter(step_code=ServiceRequestStep.STEP_ACCOUNTANT).exists())
        self.assertFalse(req.steps.filter(step_code=ServiceRequestStep.STEP_DIRECTOR).exists())

    # --- Yêu cầu: Tạm ứng là checkbox tuỳ chọn ---

    def test_advance_step_only_when_checked(self):
        req_no = self._create_request(needs_advance=False)
        self._approve_through_quote(req_no)
        self.assertFalse(req_no.steps.filter(step_code=ServiceRequestStep.STEP_ADVANCE).exists())

        req_yes = self._create_request(needs_advance=True, advance_amount=Decimal('1000000'))
        self._approve_through_quote(req_yes)
        advance = req_yes.steps.get(step_code=ServiceRequestStep.STEP_ADVANCE)
        self.assertEqual(advance.status, ServiceRequestStep.STATUS_PENDING)

    # --- Yêu cầu: Chỉ Thu mua / KT / GĐ xem giá ---

    def test_price_visibility_roles(self):
        req = self._create_request()
        self.assertFalse(can_view_pricing(self.employee, req))
        self.assertTrue(can_view_pricing(self.buyer, req))
        self.assertTrue(can_view_pricing(self.accountant, req))
        self.assertTrue(can_view_pricing(self.director, req))

    # --- Yêu cầu: Danh mục định kỳ chỉ Thu mua quản lý ---

    def test_catalog_manage_permission(self):
        self.assertTrue(can_manage_recurring_catalog(self.buyer))
        self.assertFalse(can_manage_recurring_catalog(self.employee))

    # --- Yêu cầu: Quy trình đầy đủ đến hoàn thành ---

    def test_full_workflow_to_completed(self):
        req = self._create_request()
        self._approve_through_quote(req, unit_price=Decimal('100000'))

        purchase = req.steps.get(step_code=ServiceRequestStep.STEP_PURCHASE)
        complete_purchase_step(
            purchase,
            actor=self.buyer,
            goods_receiver=self.employee,
            note='Đã đặt hàng',
        )
        req.refresh_from_db()

        receipt = req.steps.get(step_code=ServiceRequestStep.STEP_RECEIPT)
        self.assertEqual(receipt.assignee, self.employee)
        complete_execution_step(receipt, actor=self.employee, note='Đã nhận hàng')

        req.refresh_from_db()
        self.assertEqual(req.status, ServiceRequest.STATUS_COMPLETED)

    # --- Yêu cầu: Nhiều dòng, nhiều NCC, chọn 1 NCC/dòng ---

    def test_multi_line_multi_supplier_quote(self):
        req = create_request_with_steps(
            requester=self.employee,
            request_type=self.request_type,
            title='Mua nhiều món',
            description='Test',
            line_items=[
                {'description': 'Keo', 'quantity': Decimal('2'), 'unit': 'chai'},
                {'description': 'Giấy', 'quantity': Decimal('5'), 'unit': 'ram'},
            ],
        )
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        self._approve_division_head(req)

        step = req.steps.get(step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE)
        lines = list(req.line_items.all())
        complete_procurement_quote(
            step,
            actor=self.buyer,
            line_updates={
                lines[0].pk: {
                    'quantity_confirmed': Decimal('2'),
                    'quotes': [
                        {'supplier_name': 'NCC 1', 'unit_price': Decimal('50000'), 'is_selected': True},
                        {'supplier_name': 'NCC 2', 'unit_price': Decimal('60000'), 'is_selected': False},
                    ],
                },
                lines[1].pk: {
                    'quantity_confirmed': Decimal('5'),
                    'quotes': [
                        {'supplier_name': 'NCC X', 'unit_price': Decimal('100000'), 'is_selected': False},
                        {'supplier_name': 'NCC Y', 'unit_price': Decimal('80000'), 'is_selected': True},
                    ],
                },
            },
        )
        req.refresh_from_db()
        self.assertEqual(req.selected_total_amount, Decimal('500000'))

    def test_pending_widget_for_division_head_after_team_leader_approves(self):
        req = self._create_request()
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        widgets = get_portal_dashboard(self.div_head)
        titles = [w['title'] for w in widgets]
        self.assertIn('Đề xuất chờ xử lý', titles)

    def test_pending_widget_for_team_leader_on_new_request(self):
        self._create_request()
        widgets = get_portal_dashboard(self.team_leader)
        titles = [w['title'] for w in widgets]
        self.assertIn('Đề xuất chờ xử lý', titles)

    def test_create_page_renders(self):
        self.assertIsNotNone(get_active_request_type())
        self.client.force_login(self.employee)
        response = self.client.get(reverse('service_requests:create'))
        self.assertEqual(response.status_code, 200)

    def test_employee_submits_request_with_line_items(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse('service_requests:create'), {
            'title': 'Mua máy in',
            'description': 'Cần máy in A4',
            'needs_advance': '',
            'lines-TOTAL_FORMS': '1',
            'lines-INITIAL_FORMS': '0',
            'lines-MIN_NUM_FORMS': '0',
            'lines-MAX_NUM_FORMS': '20',
            'lines-0-description': 'Máy in A4',
            'lines-0-quantity': '1',
            'lines-0-unit': 'cái',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ServiceRequest.objects.filter(requester=self.employee).count(), 1)


class ItRepairWorkflowTests(TestCase):
    def setUp(self):
        self.dept_it = Department.objects.create(name='Phòng IT', sort_order=0)
        self.dept_prod = Department.objects.create(name='Xưởng SX', sort_order=1)

        for dept in (self.dept_it, self.dept_prod):
            DepartmentMenuPermission.objects.create(
                department=dept,
                modules=['de_xuat', 'ho_tro', 'equipment', 'tasks'],
            )

        perms = {
            'de_xuat': {'view': True, 'edit': True},
            'ho_tro': {'view': True, 'edit': True},
            'equipment': {'view': True, 'edit': True},
            'tasks': {'view': True, 'edit': True},
        }
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER, ROLE_DIVISION_HEAD, ROLE_DIRECTOR):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={'module_permissions': perms},
            )

        self.it_staff = self._user('it_nv', ROLE_EMPLOYEE, self.dept_it)
        self.employee = self._user('nv_prod', ROLE_EMPLOYEE, self.dept_prod)
        self.team_leader = self._user('tt_prod', ROLE_TEAM_LEADER, self.dept_prod)
        self.team_leader.profile.subordinates.set([self.employee])

        self.it_type, _ = RequestType.objects.get_or_create(
            code=RequestType.CODE_IT_REPAIR,
            defaults={'name': 'Sửa chữa IT', 'is_active': True},
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

    def _create_it_request(self, **kwargs):
        from service_requests.workflow_it import create_it_repair_request

        defaults = {
            'requester': self.employee,
            'request_type': self.it_type,
            'title': 'Máy không vào mạng',
            'description': 'Không ping được gateway',
            'incident_category': ServiceRequest.INCIDENT_NETWORK,
            'priority': ServiceRequest.PRIORITY_HIGH,
            'location_text': 'Xưởng may',
        }
        defaults.update(kwargs)
        return create_it_repair_request(**defaults)

    def test_without_team_leader_goes_straight_to_it(self):
        req = self._create_it_request(requester=self.it_staff)
        codes = list(req.steps.values_list('step_code', flat=True))
        self.assertEqual(codes, [
            ServiceRequestStep.STEP_IT_REPAIR,
        ])

    def test_with_team_leader_starts_at_tl_approval(self):
        from service_requests.workflow import approve_step

        req = self._create_it_request()
        codes = list(req.steps.values_list('step_code', flat=True))
        self.assertEqual(codes[0], ServiceRequestStep.STEP_TEAM_LEADER)
        tl_step = req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER)
        self.assertEqual(tl_step.assignee_id, self.team_leader.id)
        approve_step(tl_step, actor=self.team_leader)
        it_step = req.steps.get(step_code=ServiceRequestStep.STEP_IT_REPAIR)
        self.assertEqual(it_step.status, ServiceRequestStep.STATUS_PENDING)

    def test_it_complete_closes_request_without_requester_confirm(self):
        from service_requests.workflow import approve_step
        from service_requests.workflow_it import complete_it_repair_step

        req = self._create_it_request()
        tl_step = req.steps.filter(step_code=ServiceRequestStep.STEP_TEAM_LEADER).first()
        if tl_step:
            approve_step(tl_step, actor=self.team_leader)
        it_step = req.steps.get(step_code=ServiceRequestStep.STEP_IT_REPAIR)

        complete_it_repair_step(
            it_step,
            actor=self.it_staff,
            note='Đã cấu hình lại IP tĩnh',
            repair_cost=Decimal('0'),
        )
        req.refresh_from_db()
        self.assertEqual(req.status, ServiceRequest.STATUS_COMPLETED)
        self.assertFalse(
            req.steps.filter(step_code=ServiceRequestStep.STEP_REQUESTER_CONFIRM).exists(),
        )

    def test_create_it_repair_form(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse('service_requests:create_it_repair') + '?tab=it')
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('service_requests:create_it_repair'), {
            'repair_scope': 'it',
            'title': 'Laptop không lên nguồn',
            'description': 'Bấm nút không có đèn',
            'incident_category': ServiceRequest.INCIDENT_HW,
            'priority': ServiceRequest.PRIORITY_URGENT,
            'location_text': 'Văn phòng',
            'equipment_label': 'Laptop Dell',
            'equipment_serial': '',
            'blocks_work': 'on',
        })
        self.assertEqual(response.status_code, 302)
        req = ServiceRequest.objects.get(requester=self.employee, request_type=self.it_type)
        self.assertEqual(req.repair_equipment_scope, 'it')
        self.assertTrue(req.blocks_work)
        first_step = req.steps.exclude(status=ServiceRequestStep.STATUS_SKIPPED).order_by('step_order').first()
        self.assertIn(first_step.step_code, {
            ServiceRequestStep.STEP_TEAM_LEADER,
            ServiceRequestStep.STEP_IT_REPAIR,
        })

    def test_production_repair_form_sets_scope_and_queue(self):
        from equipment.scope import SCOPE_IT, SCOPE_PRODUCTION
        from equipment.services.managed_department import default_managed_department_for_scope
        from equipment.services.it_repair_queue import pending_it_repair_steps_for_user
        from service_requests.workflow import approve_step

        maint_dept = default_managed_department_for_scope(SCOPE_PRODUCTION)
        maint_staff = self._user('bt_nv', ROLE_EMPLOYEE, maint_dept)

        self.client.force_login(self.employee)
        response = self.client.get(reverse('service_requests:create_it_repair') + '?tab=production')
        self.assertEqual(response.status_code, 200)

        response = self.client.post(reverse('service_requests:create_it_repair'), {
            'repair_scope': 'production',
            'title': 'Máy may hỏng',
            'description': 'Không cắt chỉ',
            'incident_category': ServiceRequest.INCIDENT_M_MECH,
            'priority': ServiceRequest.PRIORITY_HIGH,
            'location_text': 'Chuyền 1',
            'equipment_label': 'Máy may Juki',
            'equipment_serial': '',
        })
        self.assertEqual(response.status_code, 302)
        req = ServiceRequest.objects.filter(
            requester=self.employee,
            repair_equipment_scope=SCOPE_PRODUCTION,
        ).latest('pk')
        it_step = req.steps.get(step_code=ServiceRequestStep.STEP_IT_REPAIR)
        self.assertEqual(it_step.target_department_id, maint_dept.id)

        tl_step = req.steps.filter(step_code=ServiceRequestStep.STEP_TEAM_LEADER).first()
        if tl_step:
            approve_step(tl_step, actor=self.team_leader)

        it_pending = pending_it_repair_steps_for_user(maint_staff, SCOPE_PRODUCTION)
        self.assertEqual(it_pending.count(), 1)
        it_queue_for_prod_req = pending_it_repair_steps_for_user(
            self.it_staff, SCOPE_IT,
        ).filter(request_id=req.pk)
        self.assertFalse(it_queue_for_prod_req.exists())

    def test_pending_for_it_staff_in_equipment_module(self):
        from service_requests.workflow import approve_step

        req = self._create_it_request()
        tl_step = req.steps.filter(step_code=ServiceRequestStep.STEP_TEAM_LEADER).first()
        if tl_step:
            approve_step(tl_step, actor=self.team_leader)
        from equipment.services.it_repair_queue import pending_it_repair_steps_for_user

        pending = pending_it_repair_steps_for_user(self.it_staff, 'it')
        self.assertEqual(pending.count(), 1)
        self.assertEqual(pending.first().step_code, ServiceRequestStep.STEP_IT_REPAIR)

    def test_it_staff_not_in_service_requests_pending(self):
        from service_requests.permissions import pending_steps_for_user

        self._create_it_request()
        pending = pending_steps_for_user(self.it_staff)
        self.assertEqual(pending.count(), 0)

