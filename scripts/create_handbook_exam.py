"""
Tạo bài kiểm tra Sổ tay nhân viên Just Play (10 câu / 10 điểm).

Chạy:
  python scripts/create_handbook_exam.py
  python scripts/create_handbook_exam.py --assign-all

VPS:
  docker compose exec -T -w /app web python scripts/create_handbook_exam.py
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'PortalJustPlay.settings')

EXAM_TITLE = 'Kiểm tra Sổ tay nhân viên Just Play'
COMPETENCY_NAME = 'Sổ tay nhân viên Just Play'

QUESTIONS = [
    {
        'content': (
            'Câu 1: Thương hiệu trang phục & phụ kiện thể thao Just Play '
            'được ra mắt vào năm nào?'
        ),
        'q_type': 'single',
        'points': 1,
        'choices': [
            ('A. 2015', False),
            ('B. 2016', False),
            ('C. 2017', True),
            ('D. 2018', False),
        ],
    },
    {
        'content': 'Câu 2: Thông điệp (slogan) chính thức của Just Play là gì?',
        'q_type': 'single',
        'points': 1,
        'choices': [
            ('A. PLAY YOUR BEST', False),
            ('B. BECOME YOUR BEST', True),
            ('C. DO YOUR BEST', False),
            ('D. COME YOUR BEST', False),
        ],
    },
    {
        'content': (
            'Câu 3: Theo cơ cấu thu nhập, nhân viên được hỗ trợ tiền cơm là bao nhiêu '
            'cho một ngày làm việc thực tế (áp dụng từ đủ 0,75 ngày công trở lên)?'
        ),
        'q_type': 'single',
        'points': 1,
        'choices': [
            ('A. 20.000₫', False),
            ('B. 25.000₫', False),
            ('C. 30.000₫', True),
            ('D. 35.000₫', False),
        ],
    },
    {
        'content': (
            'Câu 4: Công ty thực hiện chốt công cuối tháng và chi trả lương '
            'cho nhân viên vào thời gian nào?'
        ),
        'q_type': 'single',
        'points': 1,
        'choices': [
            ('A. Ngày 01 của tháng kế tiếp', False),
            ('B. Ngày 05 của tháng kế tiếp', True),
            ('C. Ngày 10 của tháng kế tiếp', False),
            ('D. Ngày 15 của tháng kế tiếp', False),
        ],
    },
    {
        'content': (
            'Câu 5: Theo quy định, khi nhân viên có nhu cầu xin nghỉ phép năm '
            'từ 02 đến 03 ngày thì cần báo trước trong khoảng thời gian bao lâu?'
        ),
        'q_type': 'single',
        'points': 1,
        'choices': [
            ('A. Báo trước 13h00 ngày hôm trước', False),
            ('B. 01 ngày làm việc', False),
            ('C. 02 ngày làm việc', True),
            ('D. 05 ngày làm việc', False),
        ],
    },
    {
        'content': (
            'Câu 6: Các khoản trợ cấp mà nhân viên có thể nhận được theo quy định '
            'của công ty là những khoản nào? (Chọn tất cả đáp án đúng)'
        ),
        'q_type': 'multiple',
        'points': 1,
        'choices': [
            ('A. Tiền cơm', True),
            ('B. Tiền điện thoại di động', False),
            ('C. Tiền nhà ở', True),
            ('D. Tiền xăng xe', True),
        ],
    },
    {
        'content': (
            'Câu 7: Các hình thức xử lý kỷ luật được áp dụng tại công ty Just Play '
            'bao gồm? (Chọn tất cả đáp án đúng)'
        ),
        'q_type': 'multiple',
        'points': 1,
        'choices': [
            ('A. Khiển trách', True),
            ('B. Kéo dài thời hạn nâng lương không quá 6 tháng', True),
            ('C. Cách chức', True),
            ('D. Sa thải', True),
        ],
    },
    {
        'content': (
            'Câu 8: Những yếu tố nào sau đây nằm trong "Giá trị cốt lõi" của Just Play? '
            '(Chọn tất cả đáp án đúng)'
        ),
        'q_type': 'multiple',
        'points': 1,
        'choices': [
            ('A. Làm thật', True),
            ('B. Chất lượng thật', True),
            ('C. Tốc độ cao', False),
            ('D. Trách nhiệm thật', True),
        ],
    },
    {
        'content': (
            'Câu 9: Khi có nguyện vọng thôi việc, nhân viên cần thực hiện đúng '
            'những quy định nào dưới đây? (Chọn tất cả đáp án đúng)'
        ),
        'q_type': 'multiple',
        'points': 1,
        'choices': [
            ('A. Báo trước 30 ngày đối với Hợp đồng lao động xác định thời hạn', True),
            ('B. Báo trước 45 ngày đối với Hợp đồng lao động không xác định thời hạn', True),
            (
                'C. Bàn giao đầy đủ công việc, trang thiết bị ghi nhận bởi biên bản bàn giao '
                'trước khi thôi việc',
                True,
            ),
            (
                'D. Báo trước 03 ngày bất kể loại hợp đồng nào nếu đã tìm được người thay thế',
                False,
            ),
        ],
    },
    {
        'content': (
            'Câu 10: Dựa vào Sổ tay nhân viên, bạn hãy trình bày chi tiết về điều kiện '
            'và các mức thưởng chuyên cần hằng tháng đối với nhân viên.'
        ),
        'q_type': 'essay',
        'points': 1,
        'choices': [],
    },
]

EXAM_DESCRIPTION = """Bài kiểm tra kiến thức Sổ tay nhân viên Just Play.

Cấu trúc đề:
• Phần 1: Trắc nghiệm chọn 1 đáp án (Câu 1–5) — 5 điểm
• Phần 2: Trắc nghiệm chọn nhiều đáp án (Câu 6–9) — 4 điểm
• Phần 3: Tự luận (Câu 10) — 1 điểm

Tổng điểm: 10 điểm (9 điểm máy chấm tự động + 1 điểm chấm tay).

——— HƯỚNG DẪN CHẤM CÂU 10 (Tự luận) ———
Học viên trả lời đủ các ý sau để đạt 1 điểm:

• Mức thưởng 500.000₫: Nhân viên không nghỉ hoặc chỉ nghỉ phép năm tối đa 01 ngày.
• Mức thưởng 300.000₫: Nghỉ khác tối đa 0,5 ngày và/hoặc phép năm nhưng tổng ngày nghỉ không vượt quá 01 ngày.
• Không được thưởng: Nghỉ sai quy định; nghỉ không có lý do chính đáng; nghỉ không được duyệt; nghỉ khác > 0,5 ngày; tổng ngày nghỉ > 01 ngày; đi trễ/về sớm quá 5 phút vượt quá 03 lần/tháng.

——— ĐÁP ÁN TRẮC NGHIỆM (tham khảo) ———
Câu 1: C | Câu 2: B | Câu 3: C | Câu 4: B | Câu 5: C
Câu 6: A, C, D | Câu 7: A, B, C, D | Câu 8: A, B, D | Câu 9: A, B, C
"""


def _setup_django():
    import django
    django.setup()


def _sync_choices(question, choices_spec: list[tuple[str, bool]]):
    from assessment.models import Choice

    question.choices.all().delete()
    Choice.objects.bulk_create([
        Choice(question=question, text=text, is_correct=correct)
        for text, correct in choices_spec
    ])


def create_exam(*, assign_all: bool = False):
    from django.contrib.auth.models import User
    from django.utils import timezone

    from assessment.models import Choice, Competency, Exam, Question
    from hrm.models import Profile

    competency, _ = Competency.objects.get_or_create(
        name=COMPETENCY_NAME,
        defaults={'description': 'Kiến thức từ Sổ tay nhân viên Just Play'},
    )

    question_objs = []
    for spec in QUESTIONS:
        question, created = Question.objects.get_or_create(
            competency=competency,
            content=spec['content'],
            defaults={
                'q_type': spec['q_type'],
                'points': spec['points'],
            },
        )
        if not created:
            question.q_type = spec['q_type']
            question.points = spec['points']
            question.save(update_fields=['q_type', 'points'])
        if spec['choices']:
            _sync_choices(question, spec['choices'])
        question_objs.append(question)

    now = timezone.now()
    exam, created = Exam.objects.update_or_create(
        title=EXAM_TITLE,
        defaults={
            'description': EXAM_DESCRIPTION,
            'start_time': now - timedelta(days=1),
            'end_time': now + timedelta(days=365),
            'duration_minutes': 30,
            'is_active': True,
        },
    )
    exam.replace_questions(question_objs)

    assigned_count = 0
    if assign_all:
        user_ids = list(
            Profile.objects.filter(is_employed=True)
            .values_list('user_id', flat=True)
            .distinct(),
        )
        users = User.objects.filter(pk__in=user_ids, is_active=True)
        exam.assigned_users.set(users)
        assigned_count = users.count()

    return exam, created, assigned_count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--assign-all',
        action='store_true',
        help='Gán bài thi cho tất cả nhân viên đang làm việc (is_employed)',
    )
    args = parser.parse_args()

    _setup_django()
    exam, created, assigned_count = create_exam(assign_all=args.assign_all)

    action = 'Tạo mới' if created else 'Cập nhật'
    print(f'{action}: {exam.title} (id={exam.id})')
    print(f'  Câu hỏi: {exam.questions.count()}')
    print(f'  Thời gian làm bài: {exam.duration_minutes} phút')
    print(f'  Hiệu lực: {exam.start_time:%d/%m/%Y} — {exam.end_time:%d/%m/%Y}')
    if args.assign_all:
        print(f'  Đã gán cho: {assigned_count} nhân viên')
    else:
        print('  Chưa gán thí sinh — vào menu Đánh giá để chọn nhân viên dự thi.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
