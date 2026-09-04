"""
Tạo dữ liệu demo cho toàn bộ chức năng PortalJustPlay (JustPlay.vn).

Usage:
    python manage.py seed_demo_data
    python manage.py seed_demo_data --clear
    python manage.py seed_demo_data --password MyPass123
"""

import sys
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from announcements.models import Announcement, AnnouncementRead
from assessment.models import (
    Choice,
    Competency,
    Exam,
    ExamSubmission,
    Question,
    UserAnswer,
)
from hrm.models import Profile
from kpi.models import MonthlyKpi, MonthlyKpiItem
from recruitment.models import Candidate, Interview, JobPosting
from reports.models import DailyWorkReport, DailyWorkReportLine
from training.models import (
    Chapter,
    Course,
    CourseCategory,
    Enrollment,
    Lesson,
    LessonProgress,
)


DEMO_PREFIX = 'demo_'
DEFAULT_PASSWORD = 'Demo@123'
REQUIRED_TABLES = (
    'announcements_announcement',
    'reports_dailyworkreport',
    'assessment_profile',
)


class Command(BaseCommand):
    help = 'Tạo dữ liệu test mẫu cho tất cả module (users, KPI, đào tạo, thi, tuyển dụng, báo cáo, thông báo).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Xóa toàn bộ user demo (username bắt đầu bằng demo_) và dữ liệu liên quan.',
        )
        parser.add_argument(
            '--password',
            default=DEFAULT_PASSWORD,
            help=f'Mật khẩu cho tài khoản demo (mặc định: {DEFAULT_PASSWORD}).',
        )

    def handle(self, *args, **options):
        if hasattr(sys.stdout, 'reconfigure'):
            try:
                sys.stdout.reconfigure(encoding='utf-8')
            except Exception:
                pass

        if options['clear']:
            self._clear_demo_data()
            return

        self._ensure_database_ready()

        password = options['password']
        with transaction.atomic():
            users = self._create_users(password)
            self._setup_profiles(users)
            self._seed_announcements(users)
            self._seed_reports(users)
            self._seed_kpi(users)
            exam = self._seed_assessment(users)
            self._seed_training(users, exam)
            self._seed_recruitment(users)

        self.stdout.write(self.style.SUCCESS('\n=== Đã tạo xong dữ liệu demo ===\n'))
        self.stdout.write('Tài khoản (mật khẩu chung): ' + password)
        self.stdout.write('')
        for key, user in users.items():
            role = getattr(user.profile, 'role', '-')
            self.stdout.write(f'  - {user.username:20} | {user.profile.full_name:25} | {role}')
        self.stdout.write('')
        self.stdout.write('Truy cập: /admin/ hoặc đăng nhập portal và thử từng menu.')

    def _ensure_database_ready(self):
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
        if plan:
            pending = sorted({f'{app}.{name}' for app, name in plan})
            raise CommandError(
                'Database chưa migrate xong. Chạy lệnh sau rồi thử lại:\n'
                '  docker compose exec web python manage.py migrate\n'
                'Hoặc deploy lại: ./deploy.sh\n\n'
                f'Migration còn thiếu ({len(pending)}): ' + ', '.join(pending[:8])
                + (' ...' if len(pending) > 8 else '')
            )

        existing = set(connection.introspection.table_names())
        missing = [name for name in REQUIRED_TABLES if name not in existing]
        if missing:
            raise CommandError(
                'Thiếu bảng trong database (code mới hơn DB). Chạy migrate:\n'
                '  docker compose exec web python manage.py migrate\n\n'
                'Bảng thiếu: ' + ', '.join(missing)
            )

    def _clear_demo_data(self):
        demo_users = User.objects.filter(username__startswith=DEMO_PREFIX)
        count = demo_users.count()
        demo_users.delete()
        Announcement.objects.filter(title__startswith='[DEMO]').delete()
        JobPosting.objects.filter(title__startswith='[DEMO]').delete()
        Competency.objects.filter(name__startswith='[DEMO]').delete()
        CourseCategory.objects.filter(name__startswith='[DEMO]').delete()
        self.stdout.write(self.style.WARNING(f'Đã xóa {count} user demo và dữ liệu gắn liền.'))

    def _create_user(self, username, full_name, password, **extra):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                'first_name': full_name.split()[-1] if full_name else username,
                'email': f'{username}@justplay.vn',
                **extra,
            },
        )
        if created or not user.check_password(password):
            user.set_password(password)
            user.save()
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.full_name = full_name
        profile.save()
        return user

    def _create_users(self, password):
        return {
            'gm': self._create_user(f'{DEMO_PREFIX}gm', 'Nguyễn Văn Giám Đốc', password),
            'hod_may': self._create_user(f'{DEMO_PREFIX}hod_may', 'Trần Thị HOD May', password),
            'hod_cat': self._create_user(f'{DEMO_PREFIX}hod_cat', 'Lê Văn HOD Cắt', password),
            'nv_may1': self._create_user(f'{DEMO_PREFIX}nv_may1', 'Phạm Thị Công Nhân May 1', password),
            'nv_may2': self._create_user(f'{DEMO_PREFIX}nv_may2', 'Hoàng Văn Công Nhân May 2', password),
            'nv_cat1': self._create_user(f'{DEMO_PREFIX}nv_cat1', 'Võ Thị Công Nhân Cắt', password),
            'nv_qc1': self._create_user(f'{DEMO_PREFIX}nv_qc1', 'Đặng Văn QC', password),
        }

    def _setup_profiles(self, users):
        users['gm'].profile.role = 'DIRECTOR'
        users['gm'].profile.position = 'HR / HCNS'
        users['gm'].profile.save()

        users['hod_may'].profile.role = 'TEAM_LEADER'
        users['hod_may'].profile.position = 'Tổ trưởng'
        users['hod_may'].profile.save()
        users['hod_may'].profile.subordinates.set([
            users['nv_may1'], users['nv_may2'], users['nv_qc1'],
        ])

        users['hod_cat'].profile.role = 'TEAM_LEADER'
        users['hod_cat'].profile.position = 'Tổ trưởng'
        users['hod_cat'].profile.save()
        users['hod_cat'].profile.subordinates.set([users['nv_cat1']])

        for key, pos in (
            ('nv_may1', 'Công nhân may'),
            ('nv_may2', 'Công nhân may'),
            ('nv_cat1', 'Công nhân cắt'),
            ('nv_qc1', 'Nhân viên QC'),
        ):
            users[key].profile.role = 'EMPLOYEE'
            users[key].profile.position = pos
            users[key].profile.save()

    def _seed_announcements(self, users):
        admin = users['gm']
        items = [
            {
                'title': '[DEMO] Quy định an toàn xưởng may Q2/2026',
                'summary': 'Bắt buộc đeo găng tay khi vận hành máy may công nghiệp.',
                'content_type': Announcement.TYPE_TEXT,
                'body': '<p>Áp dụng từ 01/06/2026 cho toàn bộ xưởng may JustPlay.</p>',
                'is_pinned': True,
            },
            {
                'title': '[DEMO] Lịch giao hàng đơn PO-JP2605',
                'summary': 'Đơn áo thun thể thao xuất EU — deadline 15/06.',
                'content_type': Announcement.TYPE_TEXT,
                'body': '<p>Ưu tiên chuyền may số 2 và QC kép trước khi đóng gói.</p>',
                'is_pinned': False,
            },
            {
                'title': '[DEMO] Thông báo nghỉ lễ 02/09',
                'summary': 'Xưởng nghỉ 1 ngày, ca kho bố trí trực.',
                'content_type': Announcement.TYPE_TEXT,
                'body': '<p>Vui lòng hoàn tất báo cáo công việc trước 17h ngày 01/09.</p>',
                'require_acknowledgment': True,
            },
        ]
        for data in items:
            ann, _ = Announcement.objects.update_or_create(
                title=data['title'],
                defaults={**data, 'created_by': admin, 'is_active': True},
            )
            AnnouncementRead.objects.get_or_create(announcement=ann, user=users['nv_may1'])

    def _seed_reports(self, users):
        today = timezone.localdate()
        report_data = [
            (users['nv_may1'], [
                ('SEW', 'PO-JP2605', 'Áo thun Dry-Fit', 420, 'PCS', 'Chuyền 2'),
                ('QC', 'PO-JP2605', 'Áo thun Dry-Fit', 400, 'PCS', 'Kiểm màu'),
            ]),
            (users['nv_may2'], [
                ('SEW', 'PO-JP2604', 'Quần jogger', 280, 'PCS', ''),
            ]),
            (users['nv_cat1'], [
                ('CUT', 'PO-JP2605', 'Áo thun Dry-Fit', 500, 'PCS', 'La bàn tự động'),
            ]),
            (users['nv_qc1'], [
                ('QC', 'PO-JP2604', 'Quần jogger', 300, 'PCS', 'AQL 2.5'),
            ]),
        ]
        for day_offset in range(3):
            report_date = today - timedelta(days=day_offset)
            submitted = day_offset > 0
            for employee, lines in report_data:
                report, _ = DailyWorkReport.objects.update_or_create(
                    employee=employee,
                    report_date=report_date,
                    defaults={
                        'shift': DailyWorkReport.SHIFT_MORNING,
                        'status': DailyWorkReport.STATUS_SUBMITTED if submitted else DailyWorkReport.STATUS_DRAFT,
                        'submitted_at': timezone.now() if submitted else None,
                        'hod_reviewed': submitted and day_offset == 1,
                    },
                )
                report.lines.all().delete()
                for idx, (area, order, product, qty, unit, note) in enumerate(lines):
                    DailyWorkReportLine.objects.create(
                        report=report,
                        area=area,
                        order_code=order,
                        product_name=product,
                        quantity=qty,
                        unit=unit,
                        note=note,
                        sort_order=idx,
                    )

    def _seed_kpi(self, users):
        now = timezone.localdate()
        year, month = now.year, now.month
        for emp_key, hod_key in [
            ('nv_may1', 'hod_may'),
            ('nv_may2', 'hod_may'),
            ('nv_cat1', 'hod_cat'),
        ]:
            board, _ = MonthlyKpi.objects.update_or_create(
                employee=users[emp_key],
                year=year,
                month=month,
                defaults={
                    'direct_manager': users[hod_key],
                    'imported_by': users[hod_key],
                    'imported_at': timezone.now(),
                },
            )
            board.items.all().delete()
            samples = [
                ('Vận hành', 40, '1. Đạt tiến độ chuyền may', 'Chậm hạn', 'Đúng hạn', 'Sớm hạn'),
                ('Chất lượng', 30, '2. Tỷ lệ lỗi QC', '>2%', '<=1.5%', '<1%'),
                ('Con người', 30, '3. Đào tạo an toàn', 'Thiếu buổi', 'Đủ buổi', 'Vượt chỉ tiêu'),
            ]
            MonthlyKpiItem.objects.bulk_create([
                MonthlyKpiItem(
                    monthly_kpi=board,
                    sort_order=i,
                    work_group=group,
                    weightage=weight,
                    indicator=indicator,
                    level_fail=fail,
                    level_pass=ok,
                    level_exceed=exc,
                    self_score=8.5,
                    mgr_score=9.0,
                )
                for i, (group, weight, indicator, fail, ok, exc) in enumerate(samples, start=1)
            ])


    def _seed_assessment(self, users):
        comp, _ = Competency.objects.get_or_create(
            name='[DEMO] An toàn & Quy trình xưởng may',
            defaults={'description': 'Kiến thức bắt buộc cho công nhân sản xuất JustPlay.'},
        )
        q1, _ = Question.objects.get_or_create(
            competency=comp,
            content='Khi máy may kẹt chỉ, nhân viên cần làm gì đầu tiên?',
            defaults={'q_type': 'single', 'points': 1},
        )
        if not q1.choices.exists():
            Choice.objects.bulk_create([
                Choice(question=q1, text='Rút phích cắm điện ngay', is_correct=True),
                Choice(question=q1, text='Dùng tay kéo vải ra', is_correct=False),
                Choice(question=q1, text='Gọi đồng nghiệp giúp kéo', is_correct=False),
            ])

        q2, _ = Question.objects.get_or_create(
            competency=comp,
            content='Liệt kê 3 bước kiểm QC áo thun trước đóng gói.',
            defaults={'q_type': 'essay', 'points': 2},
        )

        now = timezone.now()
        exam, _ = Exam.objects.update_or_create(
            title='[DEMO] Kiểm tra ATLD & QC — Tháng 6/2026',
            defaults={
                'description': 'Bài kiểm tra định kỳ cho xưởng may.',
                'start_time': now - timedelta(days=1),
                'end_time': now + timedelta(days=30),
                'duration_minutes': 30,
                'is_active': True,
            },
        )
        exam.replace_questions([q1, q2])
        employees = [users['nv_may1'], users['nv_may2'], users['nv_cat1'], users['nv_qc1']]
        exam.assigned_users.set(employees)

        submission, created = ExamSubmission.objects.get_or_create(
            user=users['nv_may1'],
            exam=exam,
            defaults={'is_completed': True, 'submitted_at': now, 'auto_score': 1.0},
        )
        if created:
            correct = q1.choices.filter(is_correct=True).first()
            ans1 = UserAnswer.objects.create(submission=submission, question=q1, essay_answer='')
            if correct:
                ans1.selected_choices.add(correct)
            UserAnswer.objects.create(
                submission=submission,
                question=q2,
                essay_answer='Kiểm đường may, nhãn size, màu sắc đồng nhất.',
                is_graded=True,
                graded_score=1.5,
            )
            submission.manual_score = 1.5
            submission.save()

        return exam

    def _seed_training(self, users, exam):
        cat, _ = CourseCategory.objects.get_or_create(
            name='[DEMO] Sản xuất JustPlay',
            defaults={'description': 'Khóa học nội bộ xưởng may.'},
        )
        course, _ = Course.objects.update_or_create(
            title='[DEMO] Quy trình may áo thun thể thao',
            defaults={
                'category': cat,
                'description': 'Hướng dẫn chuẩn JustPlay từ cắt vải đến đóng gói.',
                'final_exam': exam,
                'is_active': True,
            },
        )
        employees = [users['nv_may1'], users['nv_may2'], users['nv_cat1'], users['nv_qc1']]
        course.assigned_users.set(employees)

        ch1, _ = Chapter.objects.get_or_create(
            course=course, order=1,
            defaults={'title': 'Chương 1: Chuẩn bị chuyền may'},
        )
        ch2, _ = Chapter.objects.get_or_create(
            course=course, order=2,
            defaults={'title': 'Chương 2: QC & đóng gói'},
        )
        lessons_data = [
            (ch1, 1, 'Giới thiệu quy trình JustPlay', 'reading', 10),
            (ch1, 2, 'Thiết lập máy may công nghiệp', 'reading', 15),
            (ch2, 1, 'Checklist QC áo thun', 'reading', 12),
            (ch2, 2, 'Quy cách đóng gói xuất khẩu', 'reading', 8),
        ]
        lessons = []
        for chapter, order, title, ltype, duration in lessons_data:
            lesson, _ = Lesson.objects.update_or_create(
                chapter=chapter,
                order=order,
                defaults={
                    'title': title,
                    'lesson_type': ltype,
                    'content': f'<p>Nội dung demo: {title}</p>',
                    'duration_estimate': duration,
                },
            )
            lessons.append(lesson)

        for emp in employees:
            enr, _ = Enrollment.objects.get_or_create(user=emp, course=course)
            if emp == users['nv_may1']:
                for lesson in lessons[:2]:
                    LessonProgress.objects.update_or_create(
                        user=emp, lesson=lesson,
                        defaults={'is_completed': True},
                    )

    def _seed_recruitment(self, users):
        hr = users['gm']
        deadline = timezone.localdate() + timedelta(days=45)
        jobs = [
            {
                'title': '[DEMO] Tuyển công nhân may áo thun',
                'department': 'Xưởng May',
                'position': 'Công nhân may',
                'quantity': 5,
                'description': 'May áo thun thể thao xuất khẩu, ca ngày.',
                'requirements': 'Có kinh nghiệm máy overlock/lockstitch.',
            },
            {
                'title': '[DEMO] Tuyển nhân viên QC',
                'department': 'Kiểm soát chất lượng',
                'position': 'Công nhân may',
                'quantity': 2,
                'description': 'Kiểm hàng theo AQL, làm việc tại xưởng.',
                'requirements': 'Tỉ mỉ, biết đọc spec kỹ thuật may mặc.',
            },
        ]
        cv_content = ContentFile(b'%PDF-1.4 demo cv justplay', name='demo_cv.pdf')

        candidates_spec = [
            ('Tuyển công nhân may áo thun', 'Nguyễn Thị Mai', 'reviewing'),
            ('Tuyển công nhân may áo thun', 'Trần Văn Bình', 'interviewing'),
            ('Tuyển nhân viên QC', 'Lê Thị Hương', 'new'),
        ]

        for job_data in jobs:
            job, _ = JobPosting.objects.update_or_create(
                title=job_data['title'],
                defaults={**job_data, 'deadline': deadline, 'is_active': True},
            )

            for title_match, full_name, status in candidates_spec:
                if title_match not in job_data['title']:
                    continue
                email = full_name.lower().replace(' ', '.') + '@email.demo'
                cand, created = Candidate.objects.get_or_create(
                    job_posting=job,
                    email=email,
                    defaults={
                        'full_name': full_name,
                        'phone': '0901234567',
                        'status': status,
                        'hr_note': 'Ứng viên demo — tạo bởi seed_demo_data.',
                    },
                )
                if created or not cand.cv_file:
                    cand.cv_file.save('demo_cv.pdf', cv_content, save=True)

                if status == 'interviewing':
                    interview, _ = Interview.objects.get_or_create(
                        candidate=cand,
                        defaults={
                            'interview_time': timezone.now() + timedelta(days=3),
                            'location': 'Phòng HR — JustPlay.vn',
                            'result_notes': 'Chờ phỏng vấn vòng 2.',
                        },
                    )
                    interview.interviewers.set([hr, users['hod_may']])
