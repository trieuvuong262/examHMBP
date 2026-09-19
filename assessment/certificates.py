"""Cấp / thu hồi chứng chỉ hoàn thành kỳ thi."""
from __future__ import annotations

import secrets

from django.utils import timezone

from assessment.models import Certificate, CertificateTemplate, ExamSubmission


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
        score=f'{float(score):.1f}',
        date=date,
        code=code,
    )


def maybe_issue_certificate(submission: ExamSubmission) -> Certificate | None:
    """Cấp chứng chỉ khi bài đã chấm xong và đạt điểm. Không cấp lại nếu đang còn hiệu lực."""
    exam = submission.exam
    if not exam.issue_certificate:
        return None
    if not submission.submitted_at or not submission.is_completed:
        return None
    if float(submission.total_score) < float(exam.pass_score or 0):
        return None

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
        score=submission.total_score,
        date=date_label,
        code=code,
    )
    defaults = {
        'submission': submission,
        'template': template,
        'recipient_name': name,
        'exam_title': exam.title,
        'score': submission.total_score,
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
