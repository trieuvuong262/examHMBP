from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from assessment.portal_widgets import get_portal_dashboard
from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import (
    ROLE_DEPARTMENT_HEAD,
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_EMPLOYEE,
    ROLE_TEAM_LEADER,
)
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


@override_settings(PROCUREMENT_STAFF_USERNAMES='tm_test')
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
        for role in (
            ROLE_EMPLOYEE,
            ROLE_TEAM_LEADER,
            ROLE_DIVISION_HEAD,
            ROLE_DEPARTMENT_HEAD,
            ROLE_DIRECTOR,
        ):
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

    def _approve_department_head(self, req, *, buyer=None, actor=None):
        buyer = buyer or self.buyer
        actor = actor or self.director
        approve_step(
            req.steps.get(step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD),
            actor=actor,
            procurement_assignee=buyer,
            note='Đồng ý',
        )
        req.refresh_from_db()

    def _approve_through_quote(self, req, *, unit_price=Decimal('100000')):
        if req.steps.filter(step_code=ServiceRequestStep.STEP_TEAM_LEADER).exists():
            approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        if req.steps.filter(step_code=ServiceRequestStep.STEP_DIVISION_HEAD).exists():
            self._approve_division_head(req)
        if req.steps.filter(step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD).exists():
            self._approve_department_head(req)
        self._submit_quote(req, unit_price=unit_price)

    # --- Yêu cầu: Tổ trưởng duyệt nếu phòng có Tổ trưởng & người gửi là NV ---

    def test_employee_starts_with_team_leader_when_dept_has_tl(self):
        req = self._create_request()
        step1 = req.steps.order_by('step_order').first()
        self.assertEqual(step1.step_code, ServiceRequestStep.STEP_TEAM_LEADER)
        self.assertEqual(step1.assignee, self.team_leader)

    # --- Yêu cầu: Bỏ qua Tổ trưởng nếu phòng không có Tổ trưởng ---

    def test_dept_without_team_leader_skips_to_department_head(self):
        req = self._create_request(requester=self.employee_hr)
        codes = list(req.steps.values_list('step_code', flat=True))
        self.assertNotIn(ServiceRequestStep.STEP_TEAM_LEADER, codes)
        self.assertEqual(codes[0], ServiceRequestStep.STEP_DEPARTMENT_HEAD)

    def test_director_hidden_department_head_when_no_tbp_in_chain(self):
        """Giám đốc duyệt thay Trưởng phòng khi phòng không có TBP / TP."""
        req = self._create_request(requester=self.employee_hr)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD)
        self.assertEqual(dh.assignee, self.director)

    def test_director_pending_and_handle_department_head(self):
        from service_requests.permissions import can_handle_step, pending_steps_for_user

        req = self._create_request(requester=self.employee_hr)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DEPARTMENT_HEAD)
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

    def test_only_assigned_procurement_sees_quote_in_pending(self):
        from service_requests.permissions import pending_steps_for_user

        req = self._create_request()
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        self._approve_division_head(req)
        quote = req.steps.get(step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE)

        self.assertTrue(pending_steps_for_user(self.buyer).filter(pk=quote.pk).exists())
        self.assertFalse(pending_steps_for_user(self.accountant).filter(pk=quote.pk).exists())
        self.assertFalse(pending_steps_for_user(self.director).filter(pk=quote.pk).exists())
        self.assertFalse(pending_steps_for_user(self.employee_hr).filter(pk=quote.pk).exists())

    def test_approver_tracks_request_after_their_step(self):
        from service_requests.permissions import involved_requests_for_user, pending_steps_for_user

        req = self._create_request()
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        self._approve_division_head(req)
        quote = req.steps.get(step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE)

        self.assertFalse(pending_steps_for_user(self.div_head).filter(pk=quote.pk).exists())
        self.assertTrue(involved_requests_for_user(self.div_head).filter(pk=req.pk).exists())

        self.client.force_login(self.div_head)
        resp = self.client.get(reverse('service_requests:de_xuat_involved'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, req.title)
        self.assertContains(resp, f'#{quote.step_order}')

        detail = self.client.get(reverse('service_requests:de_xuat_detail', args=[req.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, f'Bước {quote.step_order}')
        self.assertContains(detail, reverse('service_requests:de_xuat_involved'))
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
            'needed_by': '2026-10-20',
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



@override_settings(PROCUREMENT_STAFF_USERNAMES='tm_test')
class GeneralProposalTests(TestCase):
    def setUp(self):
        self.dept_prod = Department.objects.create(name='Sản xuất', sort_order=0)
        self.dept_accounting = Department.objects.create(name='Kế toán', sort_order=1)
        self.dept_it = Department.objects.create(name='Phòng IT', sort_order=2)
        self.dept_hr = Department.objects.create(name='Hành chính nhân sự', sort_order=3)

        for dept in (self.dept_prod, self.dept_accounting, self.dept_it, self.dept_hr):
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

        self.team_leader = self._user('tt_gen', ROLE_TEAM_LEADER, self.dept_prod)
        self.div_head = self._user('tbp_gen', ROLE_DIVISION_HEAD, self.dept_prod)
        self.employee = self._user('nv_gen', ROLE_EMPLOYEE, self.dept_prod)
        self.director = self._user('gd_gen', ROLE_DIRECTOR, self.dept_prod)
        self.team_leader.profile.subordinates.set([self.employee])
        self.div_head.profile.subordinates.set([self.employee, self.team_leader])

        RequestType.objects.get_or_create(
            code=RequestType.CODE_GENERAL_PROPOSAL,
            defaults={'name': 'Đề xuất chung', 'is_active': True},
        )
        RequestType.objects.get_or_create(
            code=RequestType.CODE_ASSET_PURCHASE,
            defaults={'name': 'Đề xuất mua hàng', 'is_active': True},
        )
        self.client = Client()

    def _user(self, username, role, dept):
        user = User.objects.create_user(username=username, password='testpass123')
        Profile.objects.filter(user=user).update(
            department=dept, role=role, full_name=username, is_employed=True,
        )
        user.refresh_from_db()
        return user

    def test_create_page_renders_each_subtype(self):
        self.client.force_login(self.employee)
        for subtype in ('purchase', 'payment', 'hr', 'repair', 'account'):
            resp = self.client.get(reverse('service_requests:create') + f'?request_subtype={subtype}')
            self.assertEqual(resp.status_code, 200, subtype)

    def test_payment_proposal_creates_request_with_amount_and_steps(self):
        self.client.force_login(self.employee)
        resp = self.client.post(reverse('service_requests:create'), {
            'request_subtype': 'payment',
            'title': 'Thanh toán tiền điện',
            'description': 'Hoá đơn tháng 5',
            'payment_kind': 'payment',
            'payment_amount': '3000000',
            'payee': 'EVN',
            'payment_method': 'cash',
            'due_date': '2026-10-20',
        })
        self.assertEqual(resp.status_code, 302)
        req = ServiceRequest.objects.get(requester=self.employee)
        self.assertEqual(req.request_subtype, ServiceRequest.SUBTYPE_PAYMENT)
        self.assertEqual(req.payment_amount, Decimal('3000000'))
        self.assertEqual(req.extra_data.get('payment_kind'), 'Thanh toán')
        self.assertEqual(req.extra_data.get('payee'), 'EVN')
        # Có bước duyệt (NV thuộc phòng có TT → bắt đầu ở Tổ trưởng).
        first = req.steps.order_by('step_order').first()
        self.assertEqual(first.step_code, ServiceRequestStep.STEP_TEAM_LEADER)
        # 3M (>=2M, <10M) → có bước Kế toán duyệt chi phí.
        self.assertEqual(req.approval_tier, ServiceRequest.TIER_ACCOUNTANT)
        self.assertTrue(req.steps.filter(step_code=ServiceRequestStep.STEP_ACCOUNTANT).exists())

    def test_payment_requires_amount(self):
        self.client.force_login(self.employee)
        resp = self.client.post(reverse('service_requests:create'), {
            'request_subtype': 'payment',
            'title': 'Thiếu số tiền',
            'description': 'Test',
            'payment_kind': 'payment',
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ServiceRequest.objects.count(), 0)

    def test_repair_proposal_routes_to_technical_department(self):
        self.client.force_login(self.employee)
        resp = self.client.post(reverse('service_requests:create'), {
            'request_subtype': 'repair',
            'title': 'Máy tính hỏng',
            'description': 'Không lên nguồn',
            'incident_category': 'hw',
            'priority': ServiceRequest.PRIORITY_HIGH,
            'location_text': 'Văn phòng',
            'equipment_label': 'PC Dell',
        })
        self.assertEqual(resp.status_code, 302)
        req = ServiceRequest.objects.get(requester=self.employee)
        self.assertEqual(req.request_subtype, ServiceRequest.SUBTYPE_REPAIR)
        final = req.steps.order_by('step_order').last()
        self.assertEqual(final.step_code, ServiceRequestStep.STEP_GENERAL_EXECUTION)
        self.assertEqual(final.target_department_id, self.dept_it.id)

    def test_account_proposal_creates_request(self):
        self.client.force_login(self.employee)
        resp = self.client.post(reverse('service_requests:create'), {
            'request_subtype': 'account',
            'title': 'Cấp email nhân viên mới',
            'description': 'Nhân viên vào làm 01/06',
            'account_kind': 'email',
            'target_user': 'Nguyễn Văn A',
            'account_department': str(self.dept_prod.pk),
            'needed_date': '2026-10-20',
        })
        self.assertEqual(resp.status_code, 302)
        req = ServiceRequest.objects.get(requester=self.employee)
        self.assertEqual(req.request_subtype, ServiceRequest.SUBTYPE_ACCOUNT)
        self.assertEqual(req.extra_data.get('account_kind'), 'Email')

    def _candidate_post(self, **overrides):
        data = {
            'request_subtype': 'candidate',
            'title': 'Tuyển công nhân may',
            'description': 'May áo thun chuyền 2',
            'position': 'Công nhân may',
            'target_department': str(self.dept_prod.pk),
            'headcount': '3',
            'recruit_reason': 'addition',
            'desired_date': '2026-11-01',
            'candidate_requirements': 'Biết may 1 kim',
        }
        data.update(overrides)
        return self.client.post(reverse('service_requests:create'), data)

    def test_candidate_request_by_manager_creates_request(self):
        self.client.force_login(self.div_head)
        resp = self._candidate_post()
        self.assertEqual(resp.status_code, 302)
        req = ServiceRequest.objects.get(requester=self.div_head)
        self.assertEqual(req.request_subtype, ServiceRequest.SUBTYPE_CANDIDATE)
        self.assertEqual(req.extra_data.get('headcount'), 3)
        self.assertEqual(req.extra_data.get('target_department'), 'Sản xuất')
        final = req.steps.order_by('step_order').last()
        self.assertEqual(final.target_department_id, self.dept_hr.id)

    def test_employee_cannot_request_candidate(self):
        self.client.force_login(self.employee)
        page = self.client.get(reverse('service_requests:create'))
        self.assertNotContains(page, 'value="candidate"')
        resp = self._candidate_post()
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(ServiceRequest.objects.filter(requester=self.employee).exists())

    def test_manager_sees_candidate_subtype(self):
        self.client.force_login(self.div_head)
        page = self.client.get(reverse('service_requests:create'))
        self.assertContains(page, 'value="candidate"')

    def test_candidate_request_limited_to_managed_department(self):
        self.client.force_login(self.div_head)
        resp = self._candidate_post(target_department=str(self.dept_it.pk))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ServiceRequest.objects.filter(requester=self.div_head).exists())

    def test_completed_candidate_request_creates_draft_job(self):
        from hrm.models import Division
        from recruitment.models import JobPosting
        from service_requests.workflow import _maybe_complete_request

        div = Division.objects.create(name='Chuyền 2', department=self.dept_prod)
        self.client.force_login(self.div_head)
        self._candidate_post(target_division=str(div.pk))
        req = ServiceRequest.objects.get(requester=self.div_head)
        req.steps.all().delete()
        self.assertTrue(_maybe_complete_request(req, actor=self.director))
        job = JobPosting.objects.get(service_request=req)
        self.assertEqual(job.status, JobPosting.STATUS_DRAFT)
        self.assertEqual(job.target_division, div)
        self.assertEqual(job.quantity, 3)
        detail = self.client.get(reverse('service_requests:de_xuat_detail', args=[req.pk]))
        self.assertContains(detail, 'Tuyển dụng')
        self.assertContains(detail, job.title)

    def test_hr_subtype_is_transfer_only(self):
        self.client.force_login(self.employee)
        resp = self.client.post(reverse('service_requests:create'), {
            'request_subtype': 'hr',
            'title': 'Điều chuyển',
            'description': 'Bổ sung chuyền 3',
            'transfer_employee': 'Nguyễn A',
            'from_department': str(self.dept_prod.pk),
            'to_department': str(self.dept_hr.pk),
            'effective_date': '2026-11-01',
        })
        self.assertEqual(resp.status_code, 302)
        req = ServiceRequest.objects.get(requester=self.employee)
        self.assertEqual(req.request_subtype, ServiceRequest.SUBTYPE_HR)
        self.assertNotIn('hr_kind', req.extra_data)

    def test_general_proposal_appears_in_de_xuat_my_list(self):
        self.client.force_login(self.employee)
        self.client.post(reverse('service_requests:create'), {
            'request_subtype': 'account',
            'title': 'Cấp máy tính',
            'description': 'Máy mới',
            'account_kind': 'computer',
            'target_user': 'B',
            'device_spec': 'Laptop văn phòng',
            'account_department': str(self.dept_prod.pk),
            'needed_date': '2026-10-20',
        })
        resp = self.client.get(reverse('service_requests:de_xuat_my'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Cấp máy tính')

    # --- Hồi quy: 5 lỗi luồng đề xuất chung / quyền duyệt ---

    def _create_general(self, subtype, **extra):
        from service_requests.workflow_general import create_general_request_with_steps

        return create_general_request_with_steps(
            requester=self.employee,
            request_type=RequestType.objects.get(code=RequestType.CODE_GENERAL_PROPOSAL),
            subtype=subtype,
            title=f'Đề xuất {subtype}',
            description='Test',
            **extra,
        )

    def _approve_managers(self, req):
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        # Đề xuất chung: TBP duyệt không cần chọn Thu mua.
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD), actor=self.div_head)
        req.refresh_from_db()

    def test_division_head_approves_general_without_procurement_pick(self):
        req = self._create_general(ServiceRequest.SUBTYPE_HR)
        self._approve_managers(req)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        self.assertEqual(dh.status, ServiceRequestStep.STATUS_COMPLETED)

    def test_general_final_step_in_department_pending_and_completable(self):
        from service_requests.permissions import can_handle_step, pending_steps_for_user
        from service_requests.workflow import complete_execution_step

        hr_staff = self._user('hcns_gen', ROLE_EMPLOYEE, self.dept_hr)
        req = self._create_general(ServiceRequest.SUBTYPE_HR)
        self._approve_managers(req)
        final = req.steps.get(step_code=ServiceRequestStep.STEP_GENERAL_EXECUTION)
        self.assertEqual(final.status, ServiceRequestStep.STATUS_PENDING)
        self.assertTrue(pending_steps_for_user(hr_staff).filter(pk=final.pk).exists())
        self.assertTrue(can_handle_step(hr_staff, final))
        complete_execution_step(final, actor=hr_staff, note='Đã xử lý')
        req.refresh_from_db()
        self.assertEqual(req.status, ServiceRequest.STATUS_COMPLETED)

    def test_general_repair_completable_by_it_department(self):
        from service_requests.permissions import can_handle_step

        it_staff = self._user('it_gen', ROLE_EMPLOYEE, self.dept_it)
        req = self._create_general(ServiceRequest.SUBTYPE_REPAIR)
        self._approve_managers(req)
        final = req.steps.get(step_code=ServiceRequestStep.STEP_GENERAL_EXECUTION)
        self.assertTrue(can_handle_step(it_staff, final))

    def test_general_proposal_in_de_xuat_pending_list(self):
        self.client.force_login(self.team_leader)
        self._create_general(ServiceRequest.SUBTYPE_ACCOUNT)
        resp = self.client.get(reverse('service_requests:de_xuat_pending'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Đề xuất account')

    def test_other_division_head_cannot_handle_assigned_step(self):
        from service_requests.permissions import can_handle_step

        other_dh = self._user('tbp_khac', ROLE_DIVISION_HEAD, self.dept_hr)
        req = self._create_general(ServiceRequest.SUBTYPE_HR)
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        dh = req.steps.get(step_code=ServiceRequestStep.STEP_DIVISION_HEAD)
        self.assertEqual(dh.assignee, self.div_head)
        self.assertFalse(can_handle_step(other_dh, dh))
        self.assertTrue(can_handle_step(self.div_head, dh))
        self.assertTrue(can_handle_step(self.director, dh))


class ProposalFormRulesTests(TestCase):
    """Trường bắt buộc / điều kiện hiển thị theo loại đề xuất (proposal_forms.LAYOUT)."""

    def setUp(self):
        self.dept_a = Department.objects.create(name='Sản xuất', sort_order=0)
        self.dept_b = Department.objects.create(name='Kho', sort_order=1)

    def _form(self, subtype, data):
        from service_requests.proposal_forms import GeneralProposalForm

        base = {'title': 'T', 'description': 'D'}
        base.update(data)
        return GeneralProposalForm(base, subtype=subtype)

    def test_transfer_requires_bank_account(self):
        form = self._form('payment', {
            'payment_kind': 'payment', 'payment_amount': '1000000', 'due_date': '2026-10-20',
            'payee': 'NCC', 'payment_method': 'transfer',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('bank_account', form.errors)

    def test_cash_does_not_require_bank_account_and_drops_hidden_value(self):
        form = self._form('payment', {
            'payment_kind': 'payment', 'payment_amount': '1000000', 'due_date': '2026-10-20',
            'payee': 'NCC', 'payment_method': 'cash', 'bank_account': 'stale',
        })
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn('bank_account', form.extra_data())
        self.assertEqual(form.extra_data()['due_date'], '20/10/2026')

    def test_reimbursement_requires_advance_ref(self):
        form = self._form('payment', {
            'payment_kind': 'reimbursement', 'payment_amount': '500000', 'due_date': '2026-10-20',
            'payee': 'A', 'payment_method': 'cash',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('advance_ref', form.errors)

    def test_hr_transfer_fields_and_recruit_fields_independent(self):
        form = self._form('hr', {
            'transfer_employee': 'Nguyễn A',
            'from_department': str(self.dept_a.pk), 'to_department': str(self.dept_b.pk),
            'effective_date': '2026-11-01',
        })
        self.assertTrue(form.is_valid(), form.errors)
        extra = form.extra_data()
        self.assertEqual(extra['from_department'], 'Sản xuất')
        self.assertNotIn('position', extra)

    def test_hr_transfer_same_department_rejected(self):
        form = self._form('hr', {
            'transfer_employee': 'Nguyễn A',
            'from_department': str(self.dept_a.pk), 'to_department': str(self.dept_a.pk),
            'effective_date': '2026-11-01',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('to_department', form.errors)

    def test_candidate_requires_position_headcount(self):
        form = self._form('candidate', {})
        self.assertFalse(form.is_valid())
        for name in ('position', 'target_department', 'headcount', 'recruit_reason', 'desired_date',
                     'candidate_requirements'):
            self.assertIn(name, form.errors)
        self.assertNotIn('transfer_employee', form.errors)

    def test_account_kind_specific_requirements(self):
        form = self._form('account', {
            'account_kind': 'account', 'needed_date': '2026-10-20',
            'target_user': 'B', 'account_department': str(self.dept_a.pk),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('system_name', form.errors)
        self.assertNotIn('device_spec', form.errors)

    def test_required_markers_match_layout(self):
        form = self._form('payment', {'payment_method': 'transfer'})
        flags = {
            item['field'].name: item['required']
            for section in form.sections() for item in section['fields']
        }
        self.assertTrue(flags['payment_amount'])
        self.assertTrue(flags['bank_account'])
        self.assertFalse(flags['invoice_no'])

    def test_extra_labels_for_detail_page(self):
        from service_requests.proposal_forms import extra_field_labels

        labels = extra_field_labels('payment')
        self.assertEqual(labels['bank_account'], 'Số tài khoản · Ngân hàng')
        self.assertEqual(extra_field_labels('purchase')['needed_by'], 'Ngày cần hàng')


class ProposalFlowPreviewTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name='Sản xuất', sort_order=0)
        Department.objects.create(name='Kế toán', sort_order=1)
        self.user = User.objects.create_user(username='nv_flow', password='x')
        Profile.objects.filter(user=self.user).update(
            department=self.dept, role=ROLE_EMPLOYEE, full_name='nv_flow', is_employed=True,
        )
        self.user.refresh_from_db()

    def test_payment_preview_has_amount_tiers_and_final_step(self):
        from service_requests.workflow_general import preview_flow

        steps = preview_flow(self.user, ServiceRequest.SUBTYPE_PAYMENT)
        tiers = [s['tier'] for s in steps if s['tier']]
        self.assertEqual(tiers, ['accountant', 'director'])
        self.assertEqual(steps[-1]['label'], 'Kế toán xử lý chi')
        self.assertEqual(steps[-1]['kind'], 'execution')

    def test_purchase_preview_ends_with_receipt(self):
        from service_requests.workflow_general import preview_flow

        steps = preview_flow(self.user, ServiceRequest.SUBTYPE_PURCHASE)
        labels = [s['label'] for s in steps]
        self.assertIn('Thu mua kiểm tra giá & NCC', labels)
        self.assertEqual(labels[-1], 'Xác nhận nhận hàng')


@override_settings(PROCUREMENT_STAFF_USERNAMES='tm_test')
class RequestProgressListTests(TestCase):
    """Tiến trình trên «Đề xuất của tôi» / «Theo dõi tiến trình» (dùng lại setUp mua hàng)."""

    setUp = ServiceRequestWorkflowTests.setUp
    _user = ServiceRequestWorkflowTests._user
    _create_request = ServiceRequestWorkflowTests._create_request
    _submit_quote = ServiceRequestWorkflowTests._submit_quote
    _approve_division_head = ServiceRequestWorkflowTests._approve_division_head
    _approve_department_head = ServiceRequestWorkflowTests._approve_department_head
    _approve_through_quote = ServiceRequestWorkflowTests._approve_through_quote

    def test_purchase_progress_shows_post_quote_placeholder(self):
        from service_requests.progress import STATE_CURRENT, STATE_PLANNED, build_progress

        req = self._create_request()
        progress = build_progress(req)
        states = [n['state'] for n in progress['trail']]
        self.assertEqual(states[0], STATE_CURRENT)
        self.assertEqual(states[-1], STATE_PLANNED)
        self.assertEqual(progress['position'], 1)
        self.assertIn(self.team_leader.profile.full_name, progress['detail'])

    def test_progress_after_quote_has_real_steps_only(self):
        from service_requests.progress import STATE_PLANNED, build_progress

        req = self._create_request()
        self._approve_through_quote(req, unit_price=Decimal('100000'))
        progress = build_progress(req)
        self.assertNotIn(STATE_PLANNED, [n['state'] for n in progress['trail']])
        self.assertEqual(progress['headline'], 'Thu mua đặt hàng')

    def test_rejected_progress_shows_reason(self):
        from service_requests.progress import build_progress
        from service_requests.workflow import reject_step

        req = self._create_request()
        reject_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader, reason='Chưa cần')
        req.refresh_from_db()
        progress = build_progress(req)
        self.assertIn('Tổ trưởng duyệt', progress['headline'])
        self.assertEqual(progress['detail'], 'Lý do: Chưa cần')

    def test_my_list_renders_progress_and_filters_subtype(self):
        self._create_request(title='Mua keo dán')
        self.client.force_login(self.employee)
        resp = self.client.get(reverse('service_requests:de_xuat_my'))
        self.assertContains(resp, 'Mua keo dán')
        self.assertContains(resp, 'jp-rq-trail')
        self.assertContains(resp, 'Mua vật tư, thiết bị, văn phòng phẩm')
        resp = self.client.get(reverse('service_requests:de_xuat_my') + '?subtype=payment')
        self.assertNotContains(resp, 'Mua keo dán')

    def test_involved_list_marks_my_action_and_done_steps(self):
        req = self._create_request(title='Theo dõi keo')
        self.client.force_login(self.team_leader)
        resp = self.client.get(reverse('service_requests:de_xuat_involved') + '?can-xu-ly=1')
        self.assertContains(resp, 'Theo dõi keo')
        self.assertContains(resp, 'Chờ tôi xử lý')

        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        resp = self.client.get(reverse('service_requests:de_xuat_involved'))
        self.assertContains(resp, 'bi-check2')
        resp = self.client.get(reverse('service_requests:de_xuat_involved') + '?can-xu-ly=1')
        self.assertNotContains(resp, 'Theo dõi keo')


@override_settings(PROCUREMENT_STAFF_USERNAMES='tm_test')
class PendingListFlowTests(TestCase):
    """«Chờ tôi xử lý» phải khớp đúng người được phép xử lý ở từng bước."""

    setUp = ServiceRequestWorkflowTests.setUp
    _user = ServiceRequestWorkflowTests._user
    _create_request = ServiceRequestWorkflowTests._create_request
    _submit_quote = ServiceRequestWorkflowTests._submit_quote
    _approve_division_head = ServiceRequestWorkflowTests._approve_division_head

    def _people(self):
        return [self.team_leader, self.div_head, self.employee, self.accountant, self.buyer, self.director]

    def _assert_pending_matches_permissions(self, req):
        from service_requests.permissions import can_claim_step, can_handle_step, pending_steps_for_user

        for user in self._people():
            for step in pending_steps_for_user(user).filter(request=req):
                self.assertTrue(
                    can_handle_step(user, step) or can_claim_step(user, step),
                    f'{user.username} thấy bước {step.name} nhưng không xử lý được',
                )
        open_step = req.steps.filter(status__in=ServiceRequestStep.OPEN_HANDLER_STATUSES).first()
        if open_step:
            handlers = [u for u in self._people() if can_handle_step(u, open_step)]
            for user in handlers:
                self.assertTrue(
                    pending_steps_for_user(user).filter(pk=open_step.pk).exists(),
                    f'{user.username} xử lý được {open_step.name} nhưng không thấy trong Chờ xử lý',
                )

    def test_pending_matches_permissions_through_purchase_flow(self):
        req = self._create_request()
        self._assert_pending_matches_permissions(req)
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        self._assert_pending_matches_permissions(req)
        self._approve_division_head(req)
        self._assert_pending_matches_permissions(req)
        self._submit_quote(req, unit_price=Decimal('500000'))  # 5M → Kế toán
        self._assert_pending_matches_permissions(req)

    def test_pending_page_shows_action_and_reason(self):
        self._create_request(title='Mua băng keo')
        self.client.force_login(self.team_leader)
        resp = self.client.get(reverse('service_requests:de_xuat_pending'))
        self.assertContains(resp, 'Mua băng keo')
        self.assertContains(resp, 'Được giao cho bạn')
        self.assertEqual(resp.context['page_obj'].object_list[0].info['action'], 'Duyệt')

    def test_procurement_quote_listed_as_quote_action(self):
        req = self._create_request(title='Mua máy khoan')
        approve_step(req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER), actor=self.team_leader)
        self._approve_division_head(req)
        self.client.force_login(self.buyer)
        resp = self.client.get(reverse('service_requests:de_xuat_pending') + '?nhom=thuc-hien')
        self.assertContains(resp, 'Mua máy khoan')
        self.assertContains(resp, 'Báo giá NCC')
        resp = self.client.get(reverse('service_requests:de_xuat_pending') + '?nhom=duyet')
        self.assertNotContains(resp, 'Mua máy khoan')

    def test_director_sees_unassigned_team_leader_step(self):
        from service_requests.permissions import can_claim_step, pending_steps_for_user

        req = self._create_request()
        tl = req.steps.get(step_code=ServiceRequestStep.STEP_TEAM_LEADER)
        tl.assignee = None
        tl.save(update_fields=['assignee'])
        self.assertTrue(pending_steps_for_user(self.director).filter(pk=tl.pk).exists())
        self.assertTrue(can_claim_step(self.director, tl))
        self.assertFalse(pending_steps_for_user(self.accountant).filter(pk=tl.pk).exists())
