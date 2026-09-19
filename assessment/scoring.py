"""Chấm điểm trắc nghiệm và đồng bộ điểm bài nộp — thang 100, số nguyên."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, InvalidOperation


def round_score(value) -> float:
    """Làm tròn điểm thành số nguyên — tránh 3.9999999999999 khi cộng float."""
    try:
        number = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, TypeError, ValueError):
        number = Decimal('0')
    return float(number.quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def score_beats_pass(score, pass_score) -> bool:
    """Cấp chứng chỉ khi điểm đạt từ mức tối thiểu trở lên (mặc định ≥ 50/100)."""
    return round_score(score) >= round_score(pass_score or 0)


def grade_mc_answer(question, selected_ids) -> float:
    """Trả về điểm cho một câu trắc nghiệm (0 nếu sai/thiếu)."""
    if question.q_type not in ('single', 'multiple'):
        return 0.0

    try:
        selected = sorted({int(x) for x in selected_ids if x not in (None, '')})
    except (TypeError, ValueError):
        return 0.0

    if not selected:
        return 0.0

    correct = sorted(question.choices.filter(is_correct=True).values_list('id', flat=True))
    if question.q_type == 'single':
        if len(selected) != 1:
            return 0.0
        return round_score(question.points) if selected[0] in correct else 0.0

    return round_score(question.points) if selected == correct else 0.0


def rescore_submission(submission, *, save=True) -> dict:
    """Tính lại điểm máy chấm từ đáp án đã chọn; giữ điểm tự luận đã chấm tay."""
    from assessment.models import ExamSubmission

    if not isinstance(submission, ExamSubmission):
        raise TypeError('submission must be ExamSubmission')

    auto_score = Decimal('0')
    manual_score = Decimal('0')
    changed_answers = 0

    answers = (
        submission.answers.select_related('question')
        .prefetch_related('selected_choices', 'question__choices')
        .all()
    )
    for answer in answers:
        q = answer.question
        if q.q_type in ('single', 'multiple'):
            selected = list(answer.selected_choices.values_list('id', flat=True))
            new_score = grade_mc_answer(q, selected)
            if round_score(answer.graded_score) != new_score:
                answer.graded_score = new_score
                if save:
                    answer.save(update_fields=['graded_score'])
                changed_answers += 1
            auto_score += Decimal(str(new_score))
        elif q.q_type in ('essay', 'image', 'image_upload'):
            part = round_score(answer.graded_score or 0)
            if round_score(answer.graded_score) != part:
                answer.graded_score = part
                if save:
                    answer.save(update_fields=['graded_score'])
            manual_score += Decimal(str(part))

    auto_score_f = round_score(auto_score)
    manual_score_f = round_score(manual_score)
    submission.auto_score = auto_score_f
    submission.manual_score = manual_score_f
    if save:
        submission.save(update_fields=['auto_score', 'manual_score'])

    return {
        'auto_score': auto_score_f,
        'manual_score': manual_score_f,
        'total_score': round_score(auto_score_f + manual_score_f),
        'changed_answers': changed_answers,
    }
