"""Chấm điểm trắc nghiệm và đồng bộ điểm bài nộp."""

from __future__ import annotations


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
        return float(question.points) if selected[0] in correct else 0.0

    return float(question.points) if selected == correct else 0.0


def rescore_submission(submission, *, save=True) -> dict:
    """Tính lại điểm máy chấm từ đáp án đã chọn; giữ điểm tự luận đã chấm tay."""
    from assessment.models import ExamSubmission

    if not isinstance(submission, ExamSubmission):
        raise TypeError('submission must be ExamSubmission')

    auto_score = 0.0
    manual_score = 0.0
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
            if answer.graded_score != new_score:
                answer.graded_score = new_score
                if save:
                    answer.save(update_fields=['graded_score'])
                changed_answers += 1
            auto_score += new_score
        elif q.q_type in ('essay', 'image', 'image_upload'):
            manual_score += answer.graded_score or 0

    submission.auto_score = auto_score
    submission.manual_score = manual_score
    if save:
        submission.save(update_fields=['auto_score', 'manual_score'])

    return {
        'auto_score': auto_score,
        'manual_score': manual_score,
        'total_score': auto_score + manual_score,
        'changed_answers': changed_answers,
    }
