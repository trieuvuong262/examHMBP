"""Tạo 8 hồ sơ demo (is_demo=True) ở các bước khác nhau — không ghi tệp lên NAS, không tạo hồ sơ SX."""

from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from thiet_ke_sp.models import (
    Approval,
    ApprovalDecision,
    ApprovalStage,
    AuditLog,
    Colorway,
    DesignVersion,
    EvaluatorRole,
    MaterialLine,
    Priority,
    ProductDevelopment,
    ProductGroup,
    ProductType,
    SampleEvaluation,
    SampleVersion,
    Status,
    Task,
    TechnicalPack,
)
from thiet_ke_sp.services.workflow import _step_tasks, _role_assignee

DEMOS = [
    ('DEMO-2026-0048', 'Raider Pro 2027', ProductGroup.FOOTBALL, ProductType.SET, Status.MASTER_PENDING,
     date(2027, 1, 15), (10, 8), Priority.HIGH, 2, 2, Decimal('185000'), Decimal('178000')),
    ('DEMO-2026-0051', 'Pixel Polo Air', ProductGroup.TEAMWEAR, ProductType.POLO, Status.MASTER_PENDING,
     date(2026, 12, 20), (10, 7), Priority.NORMAL, 1, 1, Decimal('120000'), Decimal('126000')),
    ('DEMO-2026-0054', 'Velocity Tee 2027', ProductGroup.RUNNING, ProductType.SHIRT, Status.DESIGN_REVISE,
     date(2027, 1, 10), (10, 2), Priority.URGENT, 2, 0, Decimal('95000'), None),
    ('DEMO-2026-0055', 'Aurora V2', ProductGroup.VOLLEYBALL, ProductType.SET, Status.SAMPLING,
     date(2027, 2, 1), (10, 11), Priority.NORMAL, 1, 1, Decimal('170000'), None),
    ('DEMO-2026-0056', 'Ace Court Tee', ProductGroup.RACKET, ProductType.SHIRT, Status.DESIGN_PENDING,
     date(2027, 2, 15), (10, 9), Priority.NORMAL, 1, 0, Decimal('90000'), None),
    ('DEMO-2026-0042', 'Runner III', ProductGroup.RUNNING, ProductType.SHIRT, Status.APPROVED,
     date(2026, 11, 15), (10, 10), Priority.HIGH, 2, 1, Decimal('110000'), Decimal('104000')),
    ('DEMO-2026-0050', 'StormBreak V2', ProductGroup.BASKETBALL, ProductType.SET, Status.SAMPLE_REVISE,
     date(2027, 1, 28), (10, 10), Priority.NORMAL, 1, 2, Decimal('160000'), None),
    ('DEMO-2026-0058', 'Core Basic Tee', ProductGroup.BASIC, ProductType.SHIRT, Status.BRIEF_PENDING,
     date(2027, 3, 1), (10, 8), Priority.LOW, 0, 0, Decimal('55000'), None),
]

MATERIALS = [
    ('Vải mè thể thao 145gsm', True, 'Khổ 1m8', Decimal('0.65'), 'm', Decimal('62000')),
    ('Bo cổ dệt', False, 'Theo màu chính', Decimal('1'), 'cái', Decimal('4500')),
    ('Mực in chuyển nhiệt', False, '', Decimal('0.02'), 'kg', Decimal('380000')),
    ('Nhãn dệt Just Play', False, '', Decimal('1'), 'cái', Decimal('1200')),
]


class Command(BaseCommand):
    help = 'Tạo dữ liệu demo cho module Thiết kế sản phẩm (8 hồ sơ, đánh dấu is_demo).'

    def add_arguments(self, parser):
        parser.add_argument('--user', help='Username dùng làm người phụ trách / người duyệt (mặc định: superuser đầu tiên).')
        parser.add_argument('--reset', action='store_true', help='Xóa hồ sơ demo cũ trước khi tạo.')

    def handle(self, *args, **options):
        User = get_user_model()
        if options.get('user'):
            main = User.objects.filter(username=options['user']).first()
            if main is None:
                raise CommandError(f'Không tìm thấy user {options["user"]}.')
        else:
            main = User.objects.filter(is_superuser=True, is_active=True).order_by('pk').first()
            if main is None:
                raise CommandError('Không có superuser — dùng --user.')
        others = list(User.objects.filter(is_active=True).exclude(pk=main.pk).order_by('pk')[:6]) or [main]

        with transaction.atomic():
            if options['reset']:
                deleted, _ = ProductDevelopment.objects.filter(is_demo=True).delete()
                self.stdout.write(f'Đã xóa dữ liệu demo cũ ({deleted} dòng).')
            created = 0
            for index, spec in enumerate(DEMOS):
                if ProductDevelopment.objects.filter(code=spec[0]).exists():
                    continue
                self._create(spec, main, others, index)
                created += 1
        self.stdout.write(self.style.SUCCESS(f'Đã tạo {created} hồ sơ demo.'))

    def _pick(self, others, i):
        return others[i % len(others)]

    def _create(self, spec, main, others, index):
        (code, name, group, ptype, status, launch, (month, day), priority,
         design_rounds, sample_rounds, target_cost, cost) = spec
        tz_due = timezone.make_aware(datetime.combine(date(2026, month, day), time(17, 0)))
        d = ProductDevelopment.objects.create(
            code=code, name=name, product_group=group, product_type=ptype, priority=priority,
            collection='Mùa 2027', target_customer='Đội bóng phong trào, CLB doanh nghiệp',
            usage_need='Thi đấu và tập luyện cường độ cao, thoát mồ hôi nhanh.',
            market_need='Phân khúc trung cấp, kênh sỉ đội nhóm.',
            launch_date=launch, expected_qty=1500, target_wholesale_price=target_cost * 2,
            target_retail_price=target_cost * 3, target_cost=target_cost,
            description=f'Phát triển {name} cho mùa 2027.',
            proposer=self._pick(others, index), owner=main, approver=main,
            designer=self._pick(others, index + 1), technician=self._pick(others, index + 2),
            sample_maker=self._pick(others, index + 3), qa_user=self._pick(others, index + 4),
            costing_user=self._pick(others, index + 5), status=status,
            submitted_at=timezone.now(), estimated_cost=cost, is_demo=True,
        )
        def log(summary, to=''):
            AuditLog.objects.create(dossier=d, actor=main, action='demo', summary=summary, to_status=to)

        log('Tạo hồ sơ demo.', Status.DRAFT)
        if status == Status.BRIEF_PENDING:
            log('Gửi duyệt đề bài.', Status.BRIEF_PENDING)
            self._tasks(d, status, tz_due)
            return
        Approval.objects.create(dossier=d, stage=ApprovalStage.BRIEF, decision=ApprovalDecision.APPROVED,
                                decided_by=main, comment='Đồng ý phát triển.')
        log('Duyệt đề bài.', Status.DESIGNING)

        versions = []
        for no in range(1, max(design_rounds, 1) + 1):
            last = no == max(design_rounds, 1)
            state = DesignVersion.STATE_REJECTED
            if last:
                state = {
                    Status.DESIGN_REVISE: DesignVersion.STATE_DRAFT,
                    Status.DESIGN_PENDING: DesignVersion.STATE_SUBMITTED,
                }.get(status, DesignVersion.STATE_APPROVED)
            dv = DesignVersion.objects.create(
                dossier=d, version_no=no, state=state, is_current=last, created_by=d.designer,
                style_description='Raglan, cổ tim phối bo, quần ống suông.',
                pattern_description='Họa tiết gradient chéo thân trước.',
                logo_placement='Logo ngực trái 7cm, số lưng 20cm.',
                materials='Vải mè 145gsm, in chuyển nhiệt.',
                highlights='Nhẹ, thoáng khí, khô nhanh.',
                change_note='' if no == 1 else 'Đổi tông màu phối và vị trí logo theo góp ý.',
            )
            Colorway.objects.create(design_version=dv, name='Navy / Lime', color_codes='#071B36, #B9ED00', sort_order=1)
            Colorway.objects.create(design_version=dv, name='Trắng / Đỏ', color_codes='#FFFFFF, #C8102E', sort_order=2)
            if state == DesignVersion.STATE_REJECTED:
                Approval.objects.create(dossier=d, stage=ApprovalStage.DESIGN, decision=ApprovalDecision.REQUEST_CHANGE,
                                        design_version=dv, decided_by=main, comment='Chỉnh màu phối, logo nhỏ lại.')
            versions.append(dv)
        current_dv = versions[-1]
        if status in (Status.DESIGN_REVISE, Status.DESIGN_PENDING):
            log(f'Thiết kế {current_dv.label}.', status)
            self._tasks(d, status, tz_due)
            return

        Approval.objects.create(dossier=d, stage=ApprovalStage.DESIGN, decision=ApprovalDecision.APPROVED,
                                design_version=current_dv, decided_by=main)
        d.approved_design_version = current_dv
        log(f'Duyệt thiết kế {current_dv.label}.', Status.SAMPLING)

        samples = []
        for no in range(1, max(sample_rounds, 1) + 1):
            last = no == max(sample_rounds, 1)
            state = SampleVersion.STATE_FAILED
            if last:
                state = {
                    Status.SAMPLING: SampleVersion.STATE_IN_PROGRESS,
                    Status.SAMPLE_REVISE: SampleVersion.STATE_IN_PROGRESS,
                    Status.MASTER_PENDING: SampleVersion.STATE_SUBMITTED,
                }.get(status, SampleVersion.STATE_PASSED)
            sv = SampleVersion.objects.create(
                dossier=d, version_no=no, design_version=current_dv, state=state, is_current=last,
                maker=d.sample_maker, assigned_date=date(2026, 9, 20 + no),
                completed_date=None if state == SampleVersion.STATE_IN_PROGRESS else date(2026, 9, 25 + no),
                progress_note='Đang may thân, chờ in chuyển nhiệt.' if state == SampleVersion.STATE_IN_PROGRESS else '',
                change_note='' if no == 1 else 'Sửa vòng nách, nới size L 1cm.', created_by=main,
            )
            pack = TechnicalPack.objects.create(
                sample_version=sv, updated_by=d.technician,
                size_spec='S: dài áo 68 / ngực 50\nM: 70 / 52\nL: 72 / 54\nXL: 74 / 56',
                sewing_req='Mũi chỉ 12 mũi/3cm, vắt sổ 4 chỉ.', decoration_req='In chuyển nhiệt toàn thân.',
                packing_req='Gấp đôi, túi OPP, 10 bộ/bịch.',
            )
            MaterialLine.objects.bulk_create([
                MaterialLine(tech_pack=pack, material_name=m, is_main=main_flag, spec=s, consumption=c,
                             unit=u, unit_price=p, sort_order=i)
                for i, (m, main_flag, s, c, u, p) in enumerate(MATERIALS, start=1)
            ])
            if state == SampleVersion.STATE_FAILED:
                SampleEvaluation.objects.create(
                    sample_version=sv, role=EvaluatorRole.QA, evaluator=d.qa_user,
                    result=SampleEvaluation.RESULT_FAIL, defects='Vòng nách chật, đường may sườn lệch.',
                    fix_owner=d.sample_maker,
                )
            elif state in (SampleVersion.STATE_SUBMITTED, SampleVersion.STATE_PASSED):
                SampleEvaluation.objects.create(
                    sample_version=sv, role=EvaluatorRole.QA, evaluator=d.qa_user,
                    result=SampleEvaluation.RESULT_PASS, conclusion='Đạt yêu cầu chất lượng.',
                )
            samples.append(sv)
        current_sv = samples[-1]
        d.post_sample_cost = cost if status in (Status.MASTER_PENDING, Status.APPROVED) else None

        if status == Status.APPROVED:
            Approval.objects.create(dossier=d, stage=ApprovalStage.MASTER, decision=ApprovalDecision.APPROVED,
                                    design_version=current_dv, sample_version=current_sv, decided_by=main)
            d.final_sample_version = current_sv
            d.official_product_code = 'DEMO-RUNNER3'
            d.approved_at = timezone.now()
            d.is_locked = True
            log(f'Duyệt mẫu chuẩn {current_sv.label}.', Status.APPROVED)
        else:
            log(f'Mẫu {current_sv.label}.', status)
        d.save()
        self._tasks(d, status, tz_due)

    def _tasks(self, d, status, due_at):
        for spec in _step_tasks(d, status):
            assignee = _role_assignee(d, spec.role, spec.fallback_owner)
            if assignee is None and not spec.is_main:
                continue
            Task.objects.create(dossier=d, step=status, role=spec.role, title=spec.title,
                                is_main=spec.is_main, assignee=assignee, due_at=due_at)
