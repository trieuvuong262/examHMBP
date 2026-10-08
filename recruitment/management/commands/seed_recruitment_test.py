"""Dữ liệu test Tuyển dụng: 5 vị trí × 3 ứng viên, rải đều các bước của luồng.

    python manage.py seed_recruitment_test          # tạo (bỏ qua nếu đã có)
    python manage.py seed_recruitment_test --reset  # xóa dữ liệu [TEST] rồi tạo lại
    python manage.py seed_recruitment_test --clear  # chỉ xóa dữ liệu [TEST]

Chỉ chạm vào vị trí có tiêu đề bắt đầu bằng «[TEST] » và ứng viên thuộc các vị trí đó.
Đi qua recruitment.services để có đủ lịch sử / đánh giá / phỏng vấn như thao tác thật.
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hrm.models import Department
from recruitment import services
from recruitment.models import Candidate, CandidateReview, Interview, JobPosting

PREFIX = '[TEST] '
R = CandidateReview

# (tiêu đề, phòng ban, chức danh, chỉ tiêu, mô tả, yêu cầu, [ứng viên])
# Ứng viên: (họ tên, kịch bản)
JOBS = [
    ('Công nhân may chuyền 2', 'SẢN XUẤT', 'Công nhân may', 3,
     'May áo thun, áo polo theo chuyền. Ca 8h, tăng ca theo đơn.',
     'Biết may 1 kim, 2 kim. Ưu tiên có kinh nghiệm 1 năm.',
     [('Nguyễn Thị Mai', 'new'),
      ('Trần Thị Lan', 'reviewing'),
      ('Lê Văn Hùng', 'recommended')]),
    ('Nhân viên QC thành phẩm', 'ĐẢM BẢO CHẤT LƯỢNG', 'Nhân viên QC', 2,
     'Kiểm hàng thành phẩm theo AQL, ghi phiếu kiểm.',
     'Tỉ mỉ, đọc được tiêu chuẩn kỹ thuật may mặc.',
     [('Phạm Thị Hồng', 'interview_upcoming'),
      ('Võ Minh Tuấn', 'interview_awaiting_result'),
      ('Đặng Thị Thu', 'offered')]),
    ('Công nhân cắt', 'SẢN XUẤT', 'Công nhân cắt', 2,
     'Trải vải, cắt bán thành phẩm theo sơ đồ.',
     'Sức khỏe tốt, ưu tiên biết dùng máy cắt đẩy tay.',
     [('Bùi Văn Nam', 'final_rejected'),
      ('Hoàng Thị Yến', 'rejected'),
      ('Ngô Văn Lực', 'not_onboarded')]),
    ('Kế toán kho', 'TÀI CHÍNH KẾ TOÁN', 'Kế toán', 1,
     'Theo dõi nhập xuất tồn, đối chiếu chứng từ kho.',
     'Tốt nghiệp Cao đẳng/Đại học Kế toán, thành thạo Excel.',
     [('Lý Thị Ngọc', 'referral'),
      ('Trịnh Văn Khoa', 'reviewing'),
      ('Mai Thị Thảo', 'awaiting_final')]),
    ('Nhân viên kho vận', 'KẾ HOẠCH SẢN XUẤT', 'Kho vận', 2,
     'Nhận hàng, sắp xếp kho NPL, cấp phát cho chuyền.',
     'Nhanh nhẹn, chịu khó, có thể bốc xếp.',
     [('Đỗ Văn Phúc', 'new'),
      ('Châu Thị Diễm', 'awaiting_final'),
      ('Tạ Văn Long', 'interview_failed')]),
]


def _sample_cv(name, phone, email, job):
    """CV PDF 1 trang (font NotoSans trong static/fonts — hiển thị đủ dấu tiếng Việt)."""
    import io
    import unicodedata
    from pathlib import Path

    from django.conf import settings
    from django.core.files.uploadedfile import SimpleUploadedFile
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    fonts = Path(settings.BASE_DIR) / 'static' / 'fonts'
    if 'RcNoto' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('RcNoto', str(fonts / 'NotoSans-Regular.ttf')))
        pdfmetrics.registerFont(TTFont('RcNoto-B', str(fonts / 'NotoSans-Bold.ttf')))

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    y = height - 72
    pdf.setFont('RcNoto-B', 20)
    pdf.drawString(56, y, name)
    y -= 26
    pdf.setFont('RcNoto', 11)
    pdf.drawString(56, y, f'Ứng tuyển: {job.title.replace(PREFIX, "")} · {job.department_label}')
    y -= 16
    pdf.drawString(56, y, f'Điện thoại: {phone}   Email: {email}')
    sections = [
        ('Kinh nghiệm', ['2023 – nay: Công ty may Phú Thịnh — vị trí tương đương.',
                         '2021 – 2023: Xưởng may gia công Bình Dương.']),
        ('Kỹ năng', ['Thao tác máy chuyên dụng, đọc tài liệu kỹ thuật cơ bản.',
                     'Làm ca, tăng ca theo đơn hàng.']),
        ('Học vấn', ['Tốt nghiệp THPT, chứng chỉ nghề may công nghiệp.']),
    ]
    for title, lines in sections:
        y -= 34
        pdf.setFont('RcNoto-B', 13)
        pdf.drawString(56, y, title)
        pdf.setLineWidth(0.5)
        pdf.line(56, y - 4, width - 56, y - 4)
        pdf.setFont('RcNoto', 11)
        for line in lines:
            y -= 18
            pdf.drawString(68, y, f'• {line}')
    pdf.setFont('RcNoto', 8)
    pdf.drawString(56, 40, 'Hồ sơ mẫu — tạo bởi seed_recruitment_test, chỉ dùng để kiểm thử.')
    pdf.showPage()
    pdf.save()
    slug = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().replace(' ', '_')
    return SimpleUploadedFile(f'CV_{slug}.pdf', buf.getvalue(), content_type='application/pdf')


class Command(BaseCommand):
    help = 'Tạo 5 vị trí × 3 ứng viên [TEST] (kèm CV PDF mẫu) để kiểm thử module Tuyển dụng.'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true', help='Xóa dữ liệu [TEST] cũ rồi tạo lại.')
        parser.add_argument('--clear', action='store_true', help='Chỉ xóa dữ liệu [TEST].')

    def handle(self, *args, **opts):
        existing = JobPosting.objects.filter(title__startswith=PREFIX)
        if opts['clear'] or opts['reset']:
            n = self._clear(existing)
            self.stdout.write(f'Đã xóa {n} vị trí [TEST].')
            if opts['clear']:
                return
        elif existing.exists():
            self.stdout.write(self.style.WARNING('Đã có dữ liệu [TEST] — dùng --reset để tạo lại.'))
            return

        hr = User.objects.filter(is_superuser=True, is_active=True).order_by('pk').first()
        if not hr:
            raise CommandError('Cần ít nhất một tài khoản superuser đang hoạt động.')

        with transaction.atomic():
            for idx, (title, dept_name, position, qty, desc, req, people) in enumerate(JOBS, start=1):
                dept = Department.objects.filter(name__iexact=dept_name).first() or \
                    Department.objects.filter(is_active=True).order_by('sort_order').first()
                job = JobPosting.objects.create(
                    title=PREFIX + title, target_department=dept, department=dept.name if dept else '',
                    position=position, quantity=qty, description=desc, requirements=req,
                    deadline=timezone.localdate() + timedelta(days=14 + idx * 3),
                    status=JobPosting.STATUS_OPEN, created_by=hr,
                )
                manager = self._manager_for(job) or hr
                for n, (name, scenario) in enumerate(people):
                    phone = f'09{idx}{n}{idx:02d}{n:04d}'[:10]
                    self._build(job, name, phone, scenario, hr=hr, manager=manager)
                self.stdout.write(f'  {job.title} — {dept.name if dept else "?"} · đánh giá bởi {manager.username}')

        total = Candidate.objects.filter(job_posting__title__startswith=PREFIX).count()
        self.stdout.write(self.style.SUCCESS(f'Đã tạo {len(JOBS)} vị trí, {total} ứng viên [TEST].'))

    # ------------------------------------------------------------------

    @staticmethod
    def _clear(qs) -> int:
        count = 0
        for job in qs:
            for cand in job.candidates.all():
                cand.delete()  # CandidateFile xóa file qua post_delete
            job.delete()
            count += 1
        return count

    @staticmethod
    def _director():
        """Tài khoản giám đốc ductn nếu có quyền duyệt cấp 2."""
        from recruitment.permissions import can_final_approve

        user = User.objects.filter(username='ductn', is_active=True).first()
        return user if user and can_final_approve(user) else None

    @staticmethod
    def _manager_for(job):
        """Quản lý thật phụ trách vị trí (đúng phạm vi đánh giá; không lấy superuser)."""
        from recruitment.permissions import manager_can_access_job

        if not job.target_department_id:
            return None
        users = User.objects.filter(
            is_active=True, is_superuser=False, profile__is_employed=True,
            profile__department_id=job.target_department_id,
        ).select_related('profile')
        return next((u for u in users if manager_can_access_job(u, job)), None)

    def _build(self, job, name, phone, scenario, *, hr, manager):
        referral = scenario == 'referral'
        email = ''
        if n_part := name.split()[-1:]:
            email = f'{n_part[0].lower()}.test{phone[-4:]}@example.com'
        cand = services.add_candidate(
            job,
            services.CandidateInput(
                full_name=name, phone=phone, email=email,
                source=Candidate.SOURCE_REFERRAL if referral else Candidate.SOURCE_WALK_IN,
                note='Hồ sơ test — seed_recruitment_test.',
                files=[_sample_cv(name, phone, email, job)],
            ),
            actor=manager if referral else hr,
            referred_by=manager if referral else None,
        )
        if scenario in ('new', 'referral'):
            return cand

        services.transition(cand, Candidate.STATUS_REVIEWING, actor=hr)
        if scenario == 'reviewing':
            return cand
        if scenario == 'rejected':
            services.submit_review(cand, manager, decision=R.DECISION_NOT_SUITABLE, rating=2,
                                   comment='Chưa có kinh nghiệm phù hợp.')
            services.transition(cand, Candidate.STATUS_REJECTED, actor=hr, reason='Quản lý đánh giá không phù hợp.')
            return cand

        services.submit_review(cand, manager, decision=R.DECISION_RECOMMEND, rating=4,
                               comment='Hồ sơ phù hợp, mời phỏng vấn.')
        if scenario == 'recommended':
            return cand

        now = timezone.now()
        when = now + timedelta(days=2, hours=1) if scenario == 'interview_upcoming' else now - timedelta(hours=3)
        services.transition(cand, Candidate.STATUS_INTERVIEWING, actor=hr,
                            interview_time=when, interview_end=when + timedelta(minutes=45),
                            location='Phòng họp HCNS', interviewers=[manager])
        if scenario in ('interview_upcoming', 'interview_awaiting_result'):
            return cand
        if scenario == 'interview_failed':
            services.record_interview_result(cand, Interview.RESULT_FAIL, 'Thao tác chậm, chưa đạt yêu cầu.', actor=hr,
                                             check_permission=False)
            return cand

        # Đạt → chờ giám đốc duyệt; giám đốc duyệt Đạt → tự chuyển «Trúng tuyển» (khi còn chỉ tiêu).
        services.record_interview_result(cand, Interview.RESULT_PASS, 'Đạt yêu cầu chuyên môn.', actor=hr,
                                         check_permission=False)
        if scenario == 'awaiting_final':
            return cand
        director = self._director() or hr
        if scenario == 'final_rejected':
            services.record_final_decision(cand, Interview.FINAL_FAIL, 'Chưa phù hợp định hướng vị trí.',
                                           actor=director, check_permission=False)
            return cand
        services.record_final_decision(cand, Interview.FINAL_PASS, 'Đồng ý tuyển.', actor=director,
                                       check_permission=False)
        if scenario == 'not_onboarded':
            services.transition(cand, Candidate.STATUS_NOT_ONBOARDED, actor=hr,
                                reason='Ứng viên nhận việc nơi khác.')
        return cand
