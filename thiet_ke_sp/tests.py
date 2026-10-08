import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from hrm.group_permissions import PERM_ACTIONS, empty_module_perm
from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_THIET_KE_SP
from hrm.permissions import ROLE_EMPLOYEE
from san_xuat.models import ProductTechDoc
from thiet_ke_sp import permissions as perms
from thiet_ke_sp.models import (
    ApprovalDecision,
    AttachmentKind,
    EvaluatorRole,
    Priority,
    ProductDevelopment,
    ProductGroup,
    ProductType,
    ReceivingDepartment,
    SampleEvaluation,
    Status,
    Task,
)
from thiet_ke_sp.services import workflow as wf

PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4'
    b'\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
)

ALL = {'view': True, 'create': True, 'update': True, 'delete': True}


def _perm(**flags):
    base = empty_module_perm()
    for action in PERM_ACTIONS:
        base[action] = bool(flags.get(action, False))
    return base


def _group(slug, menus):
    return PermissionGroup.objects.create(
        name=slug, slug=slug,
        module_permissions={MODULE_THIET_KE_SP: {'menus': {k: _perm(**v) for k, v in menus.items()}}},
    )


def _user(username, group=None, **extra):
    user = User.objects.create_user(username=username, password='x', **extra)
    profile = Profile.objects.get(user=user)
    profile.full_name = username.title()
    profile.role = ROLE_EMPLOYEE
    profile.permission_group = group
    profile.must_change_password = False
    profile.save()
    if extra:
        User.objects.filter(pk=user.pk).update(**extra)
    return User.objects.get(pk=user.pk)


def _png(name='anh.png'):
    return SimpleUploadedFile(name, PNG, content_type='image/png')


class ThietKeSpBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        staff_group = _group('tksp-staff', {
            'dashboard': {'view': True},
            'dossiers': ALL,
            'my_tasks': {'view': True},
        })
        approver_group = _group('tksp-approver', {
            'dashboard': {'view': True},
            'dossiers': ALL,
            'my_tasks': {'view': True},
            'approve': {'view': True, 'update': True},
        })
        cls.staff = _user('nhanvien', staff_group)
        cls.qa = _user('qaqc', staff_group)
        cls.approver = _user('truongphong', approver_group)
        cls.outsider = _user('ngoai')
        cls.admin = _user('boss', is_superuser=True, is_staff=True)
        cls.receivers = {
            dept: _user(f'nhan_{dept}', staff_group) for dept in ReceivingDepartment.values
        }

    def setUp(self):
        self.nas_root = tempfile.mkdtemp(prefix='tksp-nas-')
        self.addCleanup(shutil.rmtree, self.nas_root, ignore_errors=True)
        override = override_settings(NAS_MOUNT_ROOT=self.nas_root)
        override.enable()
        self.addCleanup(override.disable)

    def make_dossier(self, submit=True, proposer=None):
        dossier = wf.create_dossier(proposer or self.staff, fields={
            'name': 'Áo bóng đá Runner',
            'product_group': ProductGroup.FOOTBALL,
            'product_type': ProductType.SHIRT,
            'collection': 'Hè 2026',
            'target_customer': 'CLB phong trào',
            'usage_need': 'Thi đấu sân cỏ nhân tạo',
            'launch_date': timezone.localdate() + timedelta(days=60),
            'priority': Priority.HIGH,
            'owner': self.staff,
            'approver': self.approver,
            'qa_user': self.qa,
        }, submit=submit)
        return ProductDevelopment.objects.get(pk=dossier.pk)

    def reload(self, dossier):
        return ProductDevelopment.objects.get(pk=dossier.pk)

    def fill_design(self, dossier):
        dv = dossier.current_design_version()
        for kind in (AttachmentKind.FRONT, AttachmentKind.BACK, AttachmentKind.DESIGN_SOURCE):
            wf.upload_attachment(dossier, self.staff, uploaded_file=_png(f'{kind}.png'), kind=kind, design_version=dv)
        cw = wf.add_colorway(dv, self.staff, name='Đỏ đen', color_codes='#C8102E / #000000')
        wf.upload_attachment(dossier, self.staff, uploaded_file=_png('cw.png'), kind=AttachmentKind.COLORWAY,
                             design_version=dv, colorway=cw)
        return dv

    def to_designing(self):
        dossier = self.make_dossier()
        wf.decide_brief(dossier, self.approver, decision=ApprovalDecision.APPROVED)
        return self.reload(dossier)

    def to_sampling(self):
        dossier = self.to_designing()
        self.fill_design(dossier)
        wf.submit_design(dossier, self.staff)
        wf.decide_design(self.reload(dossier), self.approver, decision=ApprovalDecision.APPROVED)
        return self.reload(dossier)

    def to_eval(self):
        dossier = self.to_sampling()
        sv = dossier.current_sample_version()
        wf.upload_attachment(dossier, self.staff, uploaded_file=_png('mau.png'), kind=AttachmentKind.SAMPLE_PHOTO,
                             sample_version=sv)
        wf.save_tech_pack(sv, self.staff, fields={'size_spec': 'S/M/L/XL'},
                          lines=[{'material_name': 'Vải mè thể thao', 'is_main': True, 'unit': 'm'}])
        wf.submit_sample(dossier, self.staff)
        return self.reload(dossier)

    def to_master_pending(self):
        dossier = self.to_eval()
        wf.add_evaluation(dossier, self.qa, role=EvaluatorRole.QA, result=SampleEvaluation.RESULT_PASS, items={})
        wf.update_costing(dossier, self.staff, fields={'estimated_cost': Decimal('85000')})
        wf.submit_master(self.reload(dossier), self.staff)
        return self.reload(dossier)

    def to_approved(self, code='JP-RUN-01', conditions=None):
        dossier = self.to_master_pending()
        wf.decide_master(dossier, self.approver, official_code=code, conditions=conditions)
        return self.reload(dossier)


class MainFlowTests(ThietKeSpBase):
    def test_full_flow_until_closed_creates_tech_doc(self):
        dossier = self.make_dossier()
        self.assertEqual(dossier.status, Status.BRIEF_PENDING)
        self.assertEqual(wf.current_main_task(dossier).assignee, self.approver)

        dossier = self.to_approved(code='jp-run-01')
        self.assertEqual(dossier.status, Status.APPROVED)
        self.assertEqual(dossier.official_product_code, 'JP-RUN-01')
        self.assertTrue(dossier.is_locked)

        record = wf.handover(dossier, self.staff, receivers=self.receivers)
        dossier = self.reload(dossier)
        self.assertEqual(dossier.status, Status.HANDED_OVER)
        tech_doc = ProductTechDoc.objects.get(product_code='JP-RUN-01')
        self.assertEqual(record.tech_doc, tech_doc)
        # 3 tệp thiết kế + 1 ảnh colorway + 1 ảnh mẫu
        self.assertEqual(tech_doc.design_files.count(), 5)
        self.assertEqual(tech_doc.main_material, 'Vải mè thể thao')

        with self.assertRaises(wf.WorkflowError):
            wf.close_dossier(dossier, self.staff)
        for receipt in record.receipts.all():
            with self.assertRaises(wf.WorkflowError):
                wf.confirm_receipt(receipt, self.outsider)
            wf.confirm_receipt(receipt, receipt.receiver)
        self.assertFalse(dossier.tasks.filter(state=Task.STATE_OPEN, receipt__isnull=False).exists())
        wf.close_dossier(self.reload(dossier), self.staff)
        self.assertEqual(self.reload(dossier).status, Status.CLOSED)
        self.assertFalse(dossier.tasks.filter(state=Task.STATE_OPEN).exists())

    def test_design_revision_opens_new_version(self):
        dossier = self.to_designing()
        self.fill_design(dossier)
        wf.submit_design(dossier, self.staff)
        dossier = self.reload(dossier)
        with self.assertRaises(wf.WorkflowError):
            wf.decide_design(dossier, self.approver, decision=ApprovalDecision.REQUEST_CHANGE, comment='')
        wf.decide_design(dossier, self.approver, decision=ApprovalDecision.REQUEST_CHANGE, comment='Đổi cổ tròn')
        dossier = self.reload(dossier)
        self.assertEqual(dossier.status, Status.DESIGN_REVISE)
        v2 = dossier.current_design_version()
        self.assertEqual(v2.version_no, 2)
        self.assertEqual(v2.colorways.count(), 1)
        with self.assertRaisesMessage(wf.WorkflowError, 'Nhập nội dung thay đổi'):
            wf.submit_design(dossier, self.staff)
        wf.save_design_version(v2, self.staff, fields={'change_note': 'Cổ tròn'})
        wf.submit_design(dossier, self.staff)
        self.assertEqual(self.reload(dossier).status, Status.DESIGN_PENDING)


class ControlRuleTests(ThietKeSpBase):
    def test_rule1_design_submit_requires_images_colorway_and_source(self):
        dossier = self.to_designing()
        with self.assertRaisesMessage(wf.WorkflowError, 'Ảnh mặt trước'):
            wf.submit_design(dossier, self.staff)
        self.assertEqual(self.reload(dossier).status, Status.DESIGNING)

    def test_rule2_master_requires_qa_pass_and_cost(self):
        dossier = self.to_eval()
        with self.assertRaisesMessage(wf.WorkflowError, 'QA/QC đánh giá Đạt'):
            wf.submit_master(dossier, self.staff)
        wf.add_evaluation(dossier, self.qa, role=EvaluatorRole.QA, result=SampleEvaluation.RESULT_PASS, items={})
        with self.assertRaisesMessage(wf.WorkflowError, 'Giá thành'):
            wf.submit_master(self.reload(dossier), self.staff)

    def test_rule2_failed_evaluation_blocks_master(self):
        dossier = self.to_eval()
        wf.update_costing(dossier, self.staff, fields={'estimated_cost': Decimal('85000')})
        wf.add_evaluation(dossier, self.qa, role=EvaluatorRole.QA, result=SampleEvaluation.RESULT_PASS, items={})
        wf.add_evaluation(dossier, self.staff, role=EvaluatorRole.RND, result=SampleEvaluation.RESULT_FAIL,
                          defects='Form rộng vai', items={})
        with self.assertRaisesMessage(wf.WorkflowError, 'Không còn đánh giá Không đạt'):
            wf.submit_master(self.reload(dossier), self.staff)

    def test_rule3_handover_blocked_by_open_condition_and_missing_receiver(self):
        due = timezone.now() + timedelta(days=2)
        dossier = self.to_approved(conditions=[wf.ConditionInput('Đổi chỉ may màu đen', self.staff, due)])
        cond = dossier.conditions.get()
        self.assertTrue(cond.tasks.filter(state=Task.STATE_OPEN, assignee=self.staff).exists())
        with self.assertRaisesMessage(wf.WorkflowError, 'điều kiện duyệt'):
            wf.handover(dossier, self.staff, receivers=self.receivers)

        wf.complete_condition(cond, self.staff, note='Đã đổi')
        partial = dict(self.receivers)
        partial.pop(ReceivingDepartment.QA)
        with self.assertRaisesMessage(wf.WorkflowError, 'QA/QC'):
            wf.handover(self.reload(dossier), self.staff, receivers=partial)
        self.assertFalse(ProductTechDoc.objects.filter(product_code='JP-RUN-01').exists())

        wf.handover(self.reload(dossier), self.staff, receivers=self.receivers)
        self.assertEqual(self.reload(dossier).status, Status.HANDED_OVER)

    def test_rule4_locked_after_approval_change_request_opens_new_sample(self):
        dossier = self.to_approved()
        sv = dossier.final_sample_version
        with self.assertRaises(wf.WorkflowError):
            wf.update_costing(dossier, self.staff, fields={'estimated_cost': Decimal('90000')})
        with self.assertRaises(wf.WorkflowError):
            wf.save_tech_pack(sv, self.staff, fields={'size_spec': 'đổi'}, lines=[])

        wf.request_change_after_approval(dossier, self.staff, target=wf.CHANGE_TARGET_SAMPLE, reason='Đổi vải')
        dossier = self.reload(dossier)
        self.assertEqual(dossier.status, Status.SAMPLE_REVISE)
        self.assertFalse(dossier.is_locked)
        new_sv = dossier.current_sample_version()
        self.assertEqual(new_sv.version_no, 2)
        self.assertEqual(new_sv.tech_pack.material_lines.count(), 1)
        sv.refresh_from_db()
        self.assertEqual(sv.state, sv.STATE_PASSED)

    def test_duplicate_official_code_blocked(self):
        ProductTechDoc.objects.create(product_code='JP-DUP-01', product_name='Có sẵn')
        dossier = self.to_master_pending()
        with self.assertRaisesMessage(wf.WorkflowError, 'đã có hồ sơ kỹ thuật'):
            wf.decide_master(dossier, self.approver, official_code='jp-dup-01')
        self.assertEqual(self.reload(dossier).status, Status.MASTER_PENDING)

    def test_pause_and_resume_restores_step(self):
        dossier = self.to_designing()
        wf.pause(dossier, self.approver, reason='Chờ ngân sách')
        dossier = self.reload(dossier)
        self.assertEqual(dossier.status, Status.PAUSED)
        self.assertFalse(dossier.tasks.filter(state=Task.STATE_OPEN).exists())
        wf.resume(dossier, self.approver)
        dossier = self.reload(dossier)
        self.assertEqual(dossier.status, Status.DESIGNING)
        self.assertTrue(dossier.tasks.filter(state=Task.STATE_OPEN, step=Status.DESIGNING).exists())


class PermissionTests(ThietKeSpBase):
    def test_outsider_without_module_cannot_create(self):
        self.assertFalse(perms.can_view_module(self.outsider))
        with self.assertRaises(wf.WorkflowError):
            self.make_dossier(proposer=self.outsider)

    def test_staff_is_not_approver_candidate(self):
        self.assertFalse(perms.has_approve_permission(self.staff))
        self.assertTrue(perms.has_approve_permission(self.approver))
        candidates = perms.approver_candidates()
        self.assertIn(self.approver, candidates)
        self.assertNotIn(self.staff, candidates)

        dossier = self.make_dossier(submit=False)
        dossier.approver = self.staff
        dossier.save()
        with self.assertRaisesMessage(wf.WorkflowError, 'không có quyền duyệt'):
            wf.submit_brief(dossier, self.staff)

    def test_non_approver_cannot_decide(self):
        dossier = self.make_dossier()
        with self.assertRaises(wf.WorkflowError):
            wf.decide_brief(dossier, self.staff, decision=ApprovalDecision.APPROVED)
        with self.assertRaises(wf.WorkflowError):
            wf.decide_brief(dossier, self.qa, decision=ApprovalDecision.APPROVED)

    def test_outsider_gets_denied_on_pages(self):
        self.client.force_login(self.outsider)
        resp = self.client.get(reverse('thiet_ke_sp:list'))
        self.assertNotEqual(resp.status_code, 200)


class PageRenderTests(ThietKeSpBase):
    TABS = ('overview', 'design', 'technical', 'sample', 'costing', 'approval', 'files', 'history')

    def test_pages_render_for_participants(self):
        dossier = self.to_approved(
            conditions=[wf.ConditionInput('Bổ sung tem', self.qa, timezone.now() + timedelta(days=1))],
        )
        wf.add_comment(dossier, self.qa, body='Kiểm tra lại tem')
        for user in (self.staff, self.approver, self.admin):
            self.client.force_login(user)
            for name in ('dashboard', 'list', 'create', 'my_tasks', 'approve_queue', 'notifications'):
                with self.subTest(user=user.username, page=name):
                    resp = self.client.get(reverse(f'thiet_ke_sp:{name}'))
                    expected = 302 if (user == self.staff and name == 'approve_queue') else 200
                    self.assertEqual(resp.status_code, expected, [resp.get('Location'), [str(m) for m in get_messages(resp.wsgi_request)]])
            for tab in self.TABS:
                with self.subTest(user=user.username, tab=tab):
                    resp = self.client.get(reverse('thiet_ke_sp:detail', args=[dossier.pk]), {'tab': tab})
                    self.assertEqual(resp.status_code, 200, [resp.get('Location'), [str(m) for m in get_messages(resp.wsgi_request)]])

    def test_detail_renders_at_each_stage(self):
        self.client.force_login(self.staff)
        builders = (
            lambda: self.make_dossier(submit=False),
            self.make_dossier,
            self.to_designing,
            self.to_sampling,
            self.to_eval,
            self.to_master_pending,
        )
        for build in builders:
            dossier = build()
            for tab in self.TABS:
                with self.subTest(status=dossier.status, tab=tab):
                    resp = self.client.get(reverse('thiet_ke_sp:detail', args=[dossier.pk]), {'tab': tab})
                    self.assertEqual(resp.status_code, 200, [resp.get('Location'), [str(m) for m in get_messages(resp.wsgi_request)]])

    def test_settings_page_and_attachment_serve(self):
        dossier = self.to_designing()
        att = wf.upload_attachment(dossier, self.staff, uploaded_file=_png(), kind=AttachmentKind.FRONT,
                                   design_version=dossier.current_design_version())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('thiet_ke_sp:settings')).status_code, 200)
        resp = self.client.get(reverse('thiet_ke_sp:attachment_serve', args=[att.pk]))
        self.assertEqual(resp.status_code, 200, [resp.get('Location'), [str(m) for m in get_messages(resp.wsgi_request)]])
        self.assertEqual(b''.join(resp.streaming_content), PNG)

    def test_action_view_submit_brief(self):
        dossier = self.make_dossier(submit=False)
        self.client.force_login(self.staff)
        resp = self.client.post(reverse('thiet_ke_sp:action', args=[dossier.pk, 'submit_brief']))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.reload(dossier).status, Status.BRIEF_PENDING)


class CommandTests(ThietKeSpBase):
    def test_seed_demo_renders_every_dossier(self):
        from io import StringIO

        from django.core.management import call_command

        call_command('seed_thiet_ke_sp_demo', user='boss', stdout=StringIO())
        call_command('seed_thiet_ke_sp_demo', user='boss', reset=True, stdout=StringIO())
        demos = list(ProductDevelopment.objects.filter(is_demo=True))
        self.assertEqual(len(demos), 8)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('thiet_ke_sp:list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('thiet_ke_sp:dashboard')).status_code, 200)
        for dossier in demos:
            for tab in PageRenderTests.TABS:
                with self.subTest(code=dossier.code, tab=tab):
                    resp = self.client.get(reverse('thiet_ke_sp:detail', args=[dossier.pk]), {'tab': tab})
                    self.assertEqual(resp.status_code, 200)

    def test_reminders_notify_overdue_once(self):
        from io import StringIO

        from django.core.management import call_command

        from thiet_ke_sp.models import Notification

        dossier = self.make_dossier()
        task = wf.current_main_task(dossier)
        Task.objects.filter(pk=task.pk).update(due_at=timezone.now() - timedelta(hours=1))
        before = Notification.objects.filter(user=self.approver).count()
        call_command('thiet_ke_sp_reminders', stdout=StringIO())
        after = Notification.objects.filter(user=self.approver).count()
        self.assertEqual(after, before + 1)
        call_command('thiet_ke_sp_reminders', stdout=StringIO())
        self.assertEqual(Notification.objects.filter(user=self.approver).count(), after)