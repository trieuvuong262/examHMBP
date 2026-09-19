"""Cấp / thu hồi chứng chỉ hoàn thành kỳ thi."""
from __future__ import annotations

import secrets

from django.db.models import Prefetch
from django.utils import timezone

from assessment.models import Certificate, CertificateTemplate, ExamSubmission


def _format_cert_description(raw, cert) -> str:
    text = (raw or '').strip()
    if not text or '{' not in text:
        return text
    exam_title = getattr(cert, 'exam_title', '') or ''
    name = getattr(cert, 'recipient_name', '') or ''
    score = getattr(cert, 'score', '') or ''
    code = getattr(cert, 'code', '') or ''
    issued = getattr(cert, 'issued_at', None)
    date_label = issued.strftime('%d/%m/%Y') if issued else ''
    try:
        score_label = f'{int(round(float(score)))}' if score != '' else ''
    except (TypeError, ValueError):
        score_label = str(score)
    try:
        return text.format(
            name=name,
            exam_title=exam_title,
            score=score_label,
            date=date_label,
            code=code,
        )
    except (KeyError, IndexError, ValueError):
        return text


def _description_from_template(template, exam, courses) -> str:
    if template is None or not getattr(template, 'pk', None):
        return ''
    try:
        rows = list(template.course_descriptions.all())
    except Exception:
        return ''
    source_id = getattr(getattr(exam, 'retry_of', None), 'id', None) or getattr(exam, 'id', None)
    exam_ids = {eid for eid in (getattr(exam, 'id', None), source_id) if eid}
    course_ids = {c.id for c in courses if getattr(c, 'id', None)}
    best, best_score = '', 0
    for row in rows:
        text = (row.description or '').strip()
        if not text:
            continue
        score = 0
        if row.course_id and row.course_id in course_ids:
            score += 2
        if row.exam_id and row.exam_id in exam_ids:
            score += 1
        if score > best_score:
            best, best_score = text, score
    return best


def layout_for_certificate(cert) -> dict:
    """Chương học, mô tả khóa và tiêu đề hiển thị trên chứng chỉ kiểu Coursera."""
    from training.models import Chapter, Course

    exam = getattr(cert, 'exam', None) if cert is not None else None
    template = getattr(cert, 'template', None) if cert is not None else None
    if isinstance(cert, dict):
        exam = cert.get('exam')
        template = cert.get('template')
        preset = {
            'course_title': cert.get('course_title') or cert.get('exam_title') or '',
            'description': cert.get('description') or cert.get('body_text') or '',
            'chapters': list(cert.get('chapters') or []),
        }
        if preset['chapters'] or not getattr(exam, 'pk', None):
            mapped = _description_from_template(template, exam, [])
            if mapped:
                preset['description'] = _format_cert_description(mapped, cert)
            preset['chapter_count'] = len(preset['chapters'])
            return preset

    course_title = getattr(cert, 'exam_title', '') or ''
    description = getattr(cert, 'body_text', '') or ''
    chapters: list[str] = []
    courses = []
    if getattr(exam, 'pk', None):
        source = getattr(exam, 'retry_of', None) or exam
        courses = list(source.related_courses.all())
        if not courses:
            courses = list(
                Course.objects.filter(final_exam=source)
                .prefetch_related(
                    Prefetch('chapters', queryset=Chapter.objects.order_by('order', 'id')),
                )
                .order_by('title')
            )
        if courses:
            if len(courses) == 1:
                course_title = courses[0].title or course_title
                if (courses[0].description or '').strip():
                    description = courses[0].description.strip()
            for course in courses:
                for chapter in course.chapters.all():
                    if chapter.title:
                        chapters.append(chapter.title)
    mapped = _description_from_template(template, exam, courses)
    if mapped:
        description = _format_cert_description(mapped, cert)
    return {
        'course_title': course_title,
        'description': description,
        'chapters': chapters,
        'chapter_count': len(chapters),
    }


def recipient_display_name(user) -> str:
    try:
        name = (user.profile.full_name or '').strip()
        if name:
            return name
    except Exception:
        pass
    full = (user.get_full_name() or '').strip()
    return full or user.username


def resolve_template(exam) -> CertificateTemplate | None:
    tmpl = getattr(exam, 'certificate_template', None)
    if tmpl and tmpl.is_active:
        return tmpl
    return (
        CertificateTemplate.objects.filter(is_default=True, is_active=True).first()
        or CertificateTemplate.objects.filter(is_active=True).order_by('id').first()
    )


def _new_code() -> str:
    stamp = timezone.localdate().strftime('%Y%m%d')
    for _ in range(12):
        code = f'JP-{stamp}-{secrets.token_hex(3).upper()}'
        if not Certificate.objects.filter(code=code).exists():
            return code
    return f'JP-{stamp}-{secrets.token_hex(6).upper()}'


def render_body(template: CertificateTemplate | None, *, name, exam_title, score, date, code) -> str:
    raw = (
        (template.body_text if template else '')
        or 'Chứng nhận đã hoàn thành kỳ thi «{exam_title}» với số điểm {score}.'
    )
    return raw.format(
        name=name,
        exam_title=exam_title,
        score=f'{int(round(float(score)))}',
        date=date,
        code=code,
    )


def maybe_issue_certificate(submission: ExamSubmission) -> Certificate | None:
    """Cấp chứng chỉ khi bài đã chấm xong và điểm đạt từ mức tối thiểu."""
    from assessment.scoring import round_score, score_beats_pass

    exam = submission.exam
    if not exam.issue_certificate:
        return None
    if not submission.submitted_at or not submission.is_completed:
        return None
    if not score_beats_pass(submission.total_score, exam.pass_score):
        return None
    score = round_score(submission.total_score)

    existing = Certificate.objects.filter(user=submission.user, exam=exam).first()
    template = resolve_template(exam)
    issued_at = timezone.localtime(timezone.now())
    name = recipient_display_name(submission.user)
    date_label = issued_at.strftime('%d/%m/%Y')
    code = existing.code if existing else _new_code()
    body = render_body(
        template,
        name=name,
        exam_title=exam.title,
        score=score,
        date=date_label,
        code=code,
    )
    defaults = {
        'submission': submission,
        'template': template,
        'recipient_name': name,
        'exam_title': exam.title,
        'score': score,
        'body_text': body,
        'is_revoked': False,
        'revoked_at': None,
        'revoked_by': None,
    }
    if existing:
        for key, value in defaults.items():
            setattr(existing, key, value)
        existing.save()
        return existing

    return Certificate.objects.create(
        code=code,
        user=submission.user,
        exam=exam,
        **defaults,
    )


def revoke_certificate(cert: Certificate, *, by=None) -> Certificate:
    cert.is_revoked = True
    cert.revoked_at = timezone.now()
    cert.revoked_by = by
    cert.save(update_fields=['is_revoked', 'revoked_at', 'revoked_by'])
    return cert


def ensure_retry_exam(exam):
    """Đề thi lại cho kỳ thi chính — clone câu hỏi nếu chưa có."""
    from assessment.models import Choice, Exam, ExamQuestion, Question

    source = exam.retry_of or exam
    existing = source.retry_exams.filter(is_active=True).order_by('id').first()
    if existing:
        return existing

    title = source.title
    if not title.lower().startswith('thi lại'):
        title = f'Thi lại · {title}'
    retry = Exam.objects.create(
        title=title[:255],
        description=(
            f'Bài kiểm tra lại cho học viên chưa đạt 50 điểm. '
            f'{source.description or ""}'
        )[:2000] if source.description else 'Bài kiểm tra lại cho học viên chưa đạt 50 điểm.',
        start_time=source.start_time,
        end_time=source.end_time,
        duration_minutes=source.duration_minutes,
        is_active=True,
        issue_certificate=source.issue_certificate,
        pass_score=source.pass_score or 50,
        certificate_template=source.certificate_template,
        retry_of=source,
    )
    new_links = []
    for link in source.exam_questions.select_related('question').prefetch_related('question__choices').order_by('sort_order', 'id'):
        q = link.question
        clone = Question.objects.create(
            competency=q.competency,
            content=q.content,
            q_type=q.q_type,
            points=q.points,
            image_hint=q.image_hint,
        )
        Choice.objects.bulk_create([
            Choice(question=clone, text=c.text, is_correct=c.is_correct, sort_order=c.sort_order)
            for c in q.choices.all()
        ])
        new_links.append(ExamQuestion(exam=retry, question=clone, sort_order=link.sort_order))
    if new_links:
        ExamQuestion.objects.bulk_create(new_links)
    return retry


def apply_exam_pass_or_retry(submission: ExamSubmission, *, by=None) -> dict:
    """Đạt ≥ mức điểm → cấp chứng chỉ. Không đạt → xóa lịch sử khóa, giao đề thi lại."""
    from assessment.portal_widgets import invalidate_portal_badges
    from assessment.scoring import score_beats_pass
    from training.course_exam import reset_course_progress_for_exam

    result = {
        'certificate': None,
        'must_retry': False,
        'retry_courses': [],
        'retry_exam': None,
        'passed': False,
    }
    if not submission.submitted_at or not submission.is_completed:
        return result

    if score_beats_pass(submission.total_score, submission.exam.pass_score):
        result['passed'] = True
        result['certificate'] = maybe_issue_certificate(submission)
        invalidate_portal_badges(submission.user)
        return result

    exam = submission.exam
    user = submission.user
    result['must_retry'] = True
    source = exam.retry_of or exam
    for cert in Certificate.objects.filter(
        user=user, exam__in=[source, exam], is_revoked=False,
    ):
        revoke_certificate(cert, by=by)
    result['retry_courses'] = reset_course_progress_for_exam(user, exam)
    retry = ensure_retry_exam(source)
    retry.assigned_users.add(user)
    if exam.pk != retry.pk:
        exam.assigned_users.remove(user)
    result['retry_exam'] = retry
    ExamSubmission.objects.filter(pk=submission.pk).delete()
    invalidate_portal_badges(user)
    return result
