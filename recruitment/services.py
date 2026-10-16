"""Quy tắc nghiệp vụ Tuyển dụng — mọi thay đổi trạng thái đều đi qua đây.

Luồng ứng viên:
    Mới → Chờ quản lý đánh giá → Phỏng vấn → Trúng tuyển → Đã nhận việc
    (Loại / Không nhận việc bắt buộc lý do; có thể «Mở lại» về bước đánh giá.)
    Vị trí «Bỏ qua duyệt CV»: Mới → Phỏng vấn; «Mở lại» về Mới.
    Vị trí «Bỏ qua giám đốc duyệt»: phỏng vấn Đạt → Trúng tuyển, không qua giám đốc.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    Candidate,
    CandidateEvent,
    CandidateFileKind,
    CandidateReview,
    CandidateSource,
    Interview,
    InterviewLocation,
    JobPosting,
    test_mode_enabled,
)

logger = logging.getLogger(__name__)

ONBOARDING_COURSE_TITLE = 'Đào tạo hội nhập'

C = Candidate

# Kéo thả / thao tác tay được phép. «Đã nhận việc» chỉ đạt qua onboard_candidate().
TRANSITIONS: dict[str, frozenset[str]] = {
    C.STATUS_NEW: frozenset({C.STATUS_REVIEWING, C.STATUS_REJECTED}),
    C.STATUS_REVIEWING: frozenset({C.STATUS_INTERVIEWING, C.STATUS_REJECTED}),
    C.STATUS_INTERVIEWING: frozenset({C.STATUS_OFFERED, C.STATUS_REJECTED}),
    C.STATUS_OFFERED: frozenset({C.STATUS_NOT_ONBOARDED}),
    C.STATUS_REJECTED: frozenset({C.STATUS_REVIEWING}),
    C.STATUS_NOT_ONBOARDED: frozenset({C.STATUS_REVIEWING}),
    C.STATUS_HIRED: frozenset(),
}

REASON_REQUIRED = frozenset({C.STATUS_REJECTED, C.STATUS_NOT_ONBOARDED})
ACTIVE_STATUSES = frozenset({C.STATUS_NEW, C.STATUS_REVIEWING, C.STATUS_INTERVIEWING, C.STATUS_OFFERED})


class RecruitmentError(Exception):
    """Vi phạm quy tắc nghiệp vụ — message hiển thị trực tiếp cho người dùng."""


# ---------------------------------------------------------------- helpers

def _log(candidate, kind, *, actor=None, message='', from_status='', to_status=''):
    return CandidateEvent.objects.create(
        candidate=candidate, kind=kind, actor=actor, message=message,
        from_status=from_status, to_status=to_status,
    )


def _set_status(candidate, to_status, *, actor, message):
    """Đổi trạng thái khi chỉnh quy trình vị trí — bước lùi không đi qua ``transition``."""
    from_status = candidate.status
    if from_status == to_status:
        return
    candidate.status = to_status
    candidate.status_changed_at = timezone.now()
    candidate.save(update_fields=['status', 'status_changed_at'])
    _log(
        candidate, CandidateEvent.KIND_STATUS, actor=actor, message=message,
        from_status=from_status, to_status=to_status,
    )


def _lock_candidates(ids) -> list:
    if not ids:
        return []
    return list(
        Candidate.objects.select_for_update()
        .filter(pk__in=ids)
        .select_related('job_posting')
        .order_by('pk')
    )


def _digits(phone: str) -> str:
    return re.sub(r'\D', '', phone or '')


def status_label(status: str) -> str:
    return dict(C.STATUS_CHOICES).get(status, status)


def job_transitions(job, status: str) -> frozenset[str]:
    """Bước được chuyển từ ``status`` — vị trí «Bỏ qua duyệt CV» không qua bước quản lý đánh giá."""
    targets = TRANSITIONS.get(status, frozenset())
    if not job.skip_cv_review:
        return targets
    if status == C.STATUS_NEW:
        return frozenset({C.STATUS_INTERVIEWING, C.STATUS_REJECTED})
    if status in REASON_REQUIRED:
        return frozenset({C.STATUS_NEW})
    return targets


def allowed_targets(candidate) -> list[str]:
    targets = set(job_transitions(candidate.job_posting, candidate.status))
    if C.STATUS_OFFERED in targets and candidate.status == C.STATUS_INTERVIEWING:
        interview = candidate.interview_or_none
        if not interview or not interview.is_approved:
            targets.discard(C.STATUS_OFFERED)
    return sorted(targets, key=lambda s: [k for k, _ in C.STATUS_CHOICES].index(s))


def filled_count(job: JobPosting, *, exclude_candidate_id=None) -> int:
    """Số chỉ tiêu đã dùng = Trúng tuyển + Đã nhận việc."""
    qs = job.candidates.filter(status__in=(C.STATUS_OFFERED, C.STATUS_HIRED))
    if exclude_candidate_id:
        qs = qs.exclude(pk=exclude_candidate_id)
    return qs.count()


def has_recommend_review(candidate) -> bool:
    return candidate.reviews.filter(decision=CandidateReview.DECISION_RECOMMEND).exists()


def annotate_job_counts(qs):
    return qs.annotate(
        n_candidates=Count('candidates', distinct=True),
        n_active=Count('candidates', filter=Q(candidates__status__in=ACTIVE_STATUSES), distinct=True),
        n_hired=Count('candidates', filter=Q(candidates__status=C.STATUS_HIRED), distinct=True),
        n_filled=Count(
            'candidates',
            filter=Q(candidates__status__in=(C.STATUS_OFFERED, C.STATUS_HIRED)),
            distinct=True,
        ),
    )


# ---------------------------------------------------------------- job posting

JOB_TRANSITIONS = {
    JobPosting.STATUS_DRAFT: {JobPosting.STATUS_OPEN, JobPosting.STATUS_CLOSED},
    JobPosting.STATUS_OPEN: {JobPosting.STATUS_PAUSED, JobPosting.STATUS_CLOSED},
    JobPosting.STATUS_PAUSED: {JobPosting.STATUS_OPEN, JobPosting.STATUS_CLOSED},
    JobPosting.STATUS_CLOSED: {JobPosting.STATUS_OPEN},
}


def open_blocker(job: JobPosting) -> str:
    """Lý do chưa mở tuyển được (rỗng = đủ điều kiện)."""
    missing = [
        label for label, value in (
            ('phòng ban', job.target_department_id),
            ('hạn nộp hồ sơ', job.deadline),
            ('mô tả công việc', (job.description or '').strip()),
            ('người phỏng vấn', job.pk and job.interviewers.exists()),
        ) if not value
    ]
    if missing:
        return 'Cần bổ sung ' + ', '.join(missing) + ' trước khi mở tuyển.'
    if job.is_expired:
        return 'Hạn nộp hồ sơ đã qua — cập nhật hạn mới trước khi mở tuyển.'
    return ''


def change_job_status(job: JobPosting, new_status: str, *, actor) -> JobPosting:
    if new_status not in JOB_TRANSITIONS.get(job.status, set()):
        raise RecruitmentError(
            f'Không thể chuyển vị trí từ «{job.get_status_display()}» sang '
            f'«{dict(JobPosting.STATUS_CHOICES).get(new_status, new_status)}».'
        )
    if new_status == JobPosting.STATUS_OPEN:
        blocker = open_blocker(job)
        if blocker:
            raise RecruitmentError(blocker)
    job.status = new_status
    job.closed_at = timezone.now() if new_status == JobPosting.STATUS_CLOSED else None
    job.save(update_fields=['status', 'closed_at', 'updated_at'])
    return job


def sync_job_interviewers(job: JobPosting) -> int:
    """Đổi người PV của vị trí → cập nhật các buổi PV chưa có kết quả. Trả về số buổi được cập nhật."""
    interviewers = list(job.interviewers.all())
    pending = Interview.objects.filter(
        candidate__job_posting=job, candidate__status=C.STATUS_INTERVIEWING, result=Interview.RESULT_PENDING,
    )
    count = 0
    for interview in pending:
        interview.interviewers.set(interviewers)
        count += 1
    return count


def delete_job(job: JobPosting):
    if job.candidates.exists():
        raise RecruitmentError('Vị trí đã có ứng viên — chỉ có thể đóng, không thể xóa.')
    job.delete()


def _parse_vn_date(value):
    if not value:
        return None
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def create_draft_from_service_request(service_request) -> JobPosting | None:
    """«Yêu cầu ứng viên» đã duyệt xong → vị trí ở trạng thái Nháp (idempotent).

    Vẫn nhận đề xuất cũ loại HR có ``hr_kind = Tuyển dụng`` (trước khi tách loại riêng).
    """
    from hrm.models import Department, Division
    from service_requests.models import ServiceRequest

    data = service_request.extra_data or {}
    subtype = service_request.request_subtype
    is_legacy_hr = subtype == ServiceRequest.SUBTYPE_HR and data.get('hr_kind') in ('Tuyển dụng', 'recruit')
    if subtype != ServiceRequest.SUBTYPE_CANDIDATE and not is_legacy_hr:
        return None
    existing = JobPosting.objects.filter(service_request=service_request).first()
    if existing:
        return existing

    position_text = ' '.join((data.get('position') or '').split())
    position = position_text[:100]
    try:
        quantity = max(1, int(data.get('headcount') or 1))
    except (TypeError, ValueError):
        quantity = 1
    dept_name = (data.get('target_department') or '').strip()
    department = Department.objects.filter(name__iexact=dept_name).first() if dept_name else None
    div_name = (data.get('target_division') or '').strip()
    division = (
        Division.objects.filter(department=department, name__iexact=div_name).first()
        if department and div_name else None
    )

    description_parts = [
        f'Lý do tuyển: {data["recruit_reason"]}' if data.get('recruit_reason') else '',
        (service_request.description or '').strip(),
    ]
    return JobPosting.objects.create(
        title=position_text or service_request.title,
        target_department=department,
        target_division=division,
        department=dept_name,
        position=position,
        quantity=quantity,
        description='\n'.join(p for p in description_parts if p),
        requirements=(data.get('candidate_requirements') or '').strip(),
        deadline=_parse_vn_date(data.get('desired_date')),
        status=JobPosting.STATUS_DRAFT,
        service_request=service_request,
        created_by=service_request.requester,
    )


# ---------------------------------------------------------------- candidate

@dataclass
class CandidateInput:
    full_name: str
    phone: str
    email: str = ''
    gender: str = ''
    date_of_birth: date | None = None
    files: list = field(default_factory=list)
    note: str = ''
    source: str = C.SOURCE_HR


# ---------------------------------------------------------------- hồ sơ đính kèm

MAX_FILES_PER_CANDIDATE = 10
MAX_FILE_BYTES = 10 * 1024 * 1024


def validate_candidate_files(files, *, request=None) -> list:
    """Whitelist PDF/Word/ảnh + chữ ký file + quét virus (nas_storage.upload_guard).

    Raise RecruitmentError với lý do từng file bị chặn.
    """
    import os

    from nas_storage.upload_guard import GROUP_DOC, GROUP_IMAGE, partition_uploads

    from .models import CANDIDATE_FILE_TYPES

    files = [f for f in (files or []) if f]
    wrong_type = [f.name for f in files if os.path.splitext(f.name or '')[1].lower() not in CANDIDATE_FILE_TYPES]
    if wrong_type:
        raise RecruitmentError('Chỉ nhận PDF, Word hoặc ảnh JPG/PNG: ' + ', '.join(wrong_type))
    accepted, rejected = partition_uploads(
        files, groups=(GROUP_DOC, GROUP_IMAGE), max_bytes=MAX_FILE_BYTES, request=request,
    )
    if rejected:
        raise RecruitmentError(' '.join(rejected))
    return accepted


def attach_files(candidate, files, *, actor, kind=None, request=None) -> list:
    from .models import CandidateFile

    return _store_files(candidate, validate_candidate_files(files, request=request), actor=actor, kind=kind)


def _store_files(candidate, accepted, *, actor, kind=None) -> list:
    from .models import CandidateFile

    if not accepted:
        return []
    if candidate.files.count() + len(accepted) > MAX_FILES_PER_CANDIDATE:
        raise RecruitmentError(f'Mỗi ứng viên tối đa {MAX_FILES_PER_CANDIDATE} file.')
    if not CandidateFileKind.objects.filter(code=kind, is_active=True).exists():
        kind = CandidateFile.KIND_CV
    created = []
    for upload in accepted:
        obj = CandidateFile(
            candidate=candidate, kind=kind, original_name=(upload.name or 'ho-so')[:255],
            size=getattr(upload, 'size', 0) or 0, uploaded_by=actor,
        )
        obj.file.save(upload.name, upload, save=False)
        obj.save()
        created.append(obj)
    _log(candidate, CandidateEvent.KIND_FILE, actor=actor,
         message='Tải lên: ' + ', '.join(f.original_name for f in created))
    return created


def remove_file(candidate_file, *, actor):
    candidate = candidate_file.candidate
    name = candidate_file.original_name
    candidate_file.delete()
    _log(candidate, CandidateEvent.KIND_FILE, actor=actor, message=f'Xóa: {name}')


@transaction.atomic
def add_candidate(job: JobPosting, data: CandidateInput, *, actor, referred_by=None, request=None) -> Candidate:
    # Kiểm tra file trước khi ghi DB — file lỗi thì không tạo ứng viên dở dang.
    files = validate_candidate_files(data.files, request=request) if data.files else []
    job = JobPosting.objects.select_for_update().get(pk=job.pk)
    if not job.accepts_candidates:
        raise RecruitmentError(f'Vị trí «{job.title}» không nhận hồ sơ (chưa mở hoặc đã hết hạn).')
    if not data.full_name.strip() or len(_digits(data.phone)) < 9:
        raise RecruitmentError('Cần họ tên và số điện thoại hợp lệ.')
    _reject_duplicate_contact(job, phone=data.phone.strip(), email=(data.email or '').strip())

    candidate = Candidate.objects.create(
        job_posting=job,
        full_name=data.full_name.strip(),
        gender=data.gender or '',
        date_of_birth=data.date_of_birth,
        phone=data.phone.strip(),
        email=(data.email or '').strip(),
        note=(data.note or '').strip(),
        source=data.source,
        referred_by=referred_by,
        status=C.STATUS_NEW,
        status_changed_at=timezone.now(),
    )
    _log(candidate, CandidateEvent.KIND_CREATED, actor=actor, to_status=C.STATUS_NEW,
         message=candidate.source_label)
    if data.note.strip():
        _log(candidate, CandidateEvent.KIND_NOTE, actor=actor, message=data.note.strip())
    _store_files(candidate, files, actor=actor)
    return candidate


def profile_locked(candidate) -> bool:
    """Đã onboard — hồ sơ tuyển dụng không sửa / xóa (nhân viên nằm ở Danh sách nhân viên)."""
    return bool(candidate.employee_id) or candidate.status == C.STATUS_HIRED


def _reject_duplicate_contact(job, *, phone: str, email: str, exclude_pk=None):
    phone_digits = _digits(phone)
    others = job.candidates.only('phone', 'email')
    if exclude_pk:
        others = others.exclude(pk=exclude_pk)
    for other in others:
        if _digits(other.phone) == phone_digits:
            raise RecruitmentError(f'Số điện thoại {phone} đã nộp cho vị trí này.')
        if email and other.email and other.email.lower() == email.lower():
            raise RecruitmentError(f'Email {email} đã nộp cho vị trí này.')


@transaction.atomic
def update_candidate(candidate, job: JobPosting, data: CandidateInput, *, actor) -> Candidate:
    candidate = Candidate.objects.select_for_update().get(pk=candidate.pk)
    if profile_locked(candidate):
        raise RecruitmentError('Ứng viên đã nhận việc — không sửa hồ sơ tuyển dụng.')
    full_name = data.full_name.strip()
    phone = data.phone.strip()
    email = (data.email or '').strip()
    note = (data.note or '').strip()
    if not full_name or len(_digits(phone)) < 9:
        raise RecruitmentError('Cần họ tên và số điện thoại hợp lệ.')
    job = JobPosting.objects.select_for_update().get(pk=job.pk)
    if job.pk != candidate.job_posting_id and not job.accepts_candidates:
        raise RecruitmentError(f'Vị trí «{job.title}» không nhận hồ sơ (chưa mở hoặc đã hết hạn).')
    _reject_duplicate_contact(job, phone=phone, email=email, exclude_pk=candidate.pk)

    old_note = candidate.note
    candidate.job_posting = job
    candidate.full_name = full_name
    candidate.gender = data.gender or ''
    candidate.date_of_birth = data.date_of_birth
    candidate.phone = phone
    candidate.email = email
    candidate.note = note
    candidate.source = data.source or candidate.source
    candidate.save(update_fields=[
        'job_posting', 'full_name', 'gender', 'date_of_birth', 'phone', 'email', 'note', 'source',
    ])
    if note != old_note:
        _log(
            candidate, CandidateEvent.KIND_NOTE, actor=actor,
            message=note or 'Đã xóa ghi chú.',
        )
    return candidate


@transaction.atomic
def delete_candidate(candidate):
    candidate = Candidate.objects.select_for_update().get(pk=candidate.pk)
    if profile_locked(candidate):
        raise RecruitmentError('Ứng viên đã nhận việc — không xóa hồ sơ tuyển dụng.')
    candidate.delete()


def add_note(candidate, message: str, *, actor):
    message = (message or '').strip()
    if not message:
        raise RecruitmentError('Ghi chú trống.')
    candidate.note = message
    candidate.save(update_fields=['note'])
    return _log(candidate, CandidateEvent.KIND_NOTE, actor=actor, message=message)


INTERVIEW_MIN_MINUTES = 15
INTERVIEW_MAX_MINUTES = 8 * 60


def _cancel_pending_director(candidate, *, actor) -> None:
    """Loại thì không còn chờ giám đốc duyệt."""
    interview = candidate.interview_or_none
    if not interview or interview.final_result != Interview.FINAL_PENDING:
        return
    interview.final_result = Interview.FINAL_NONE
    interview.final_notes = ''
    interview.final_by = None
    interview.final_at = None
    interview.save(update_fields=['final_result', 'final_notes', 'final_by', 'final_at'])
    _log(
        candidate, CandidateEvent.KIND_INTERVIEW, actor=actor,
        message='Hủy chờ giám đốc duyệt — hồ sơ đã loại.',
    )


def validate_interview_slot(start, end):
    if not start:
        raise RecruitmentError('Cần chọn thời gian bắt đầu phỏng vấn.')
    if not end:
        raise RecruitmentError('Cần chọn thời gian kết thúc phỏng vấn.')
    minutes = (end - start).total_seconds() / 60
    if minutes <= 0:
        raise RecruitmentError('Thời gian kết thúc phải sau thời gian bắt đầu.')
    if minutes < INTERVIEW_MIN_MINUTES:
        raise RecruitmentError(f'Buổi phỏng vấn tối thiểu {INTERVIEW_MIN_MINUTES} phút.')
    if minutes > INTERVIEW_MAX_MINUTES:
        raise RecruitmentError(f'Buổi phỏng vấn tối đa {INTERVIEW_MAX_MINUTES // 60} giờ.')


@transaction.atomic
def transition(candidate, to_status: str, *, actor, reason: str = '',
               interview_time=None, interview_end=None, location: str = '') -> Candidate:
    """Người phỏng vấn lấy theo vị trí tuyển dụng (``JobPosting.interviewers``)."""
    candidate = Candidate.objects.select_for_update().select_related('job_posting').get(pk=candidate.pk)
    from_status = candidate.status
    if to_status == C.STATUS_HIRED:
        raise RecruitmentError('Chuyển sang «Đã nhận việc» bằng thao tác Onboard.')
    if to_status not in job_transitions(candidate.job_posting, from_status):
        raise RecruitmentError(
            f'Không thể chuyển từ «{status_label(from_status)}» sang «{status_label(to_status)}».'
        )
    reason = (reason or '').strip()
    if to_status in REASON_REQUIRED and not reason:
        raise RecruitmentError(f'Cần nhập lý do khi chuyển sang «{status_label(to_status)}».')

    job = candidate.job_posting
    if to_status == C.STATUS_REVIEWING and from_status == C.STATUS_NEW and not job.target_department_id:
        raise RecruitmentError('Vị trí chưa gắn phòng ban — không có quản lý nhận đánh giá.')

    if to_status == C.STATUS_INTERVIEWING:
        if not job.skip_cv_review and not has_recommend_review(candidate):
            raise RecruitmentError('Cần ít nhất 1 đánh giá «Đạt» của quản lý.')
        interviewers = list(job.interviewers.all())
        if not interviewers:
            raise RecruitmentError(
                f'Vị trí «{job.title}» chưa chọn người phỏng vấn — cập nhật ở trang vị trí tuyển dụng.'
            )
        validate_interview_slot(interview_time, interview_end)
        interview, _ = Interview.objects.update_or_create(
            candidate=candidate,
            defaults={
                'interview_time': interview_time,
                'end_time': interview_end,
                'location': (location or '').strip(),
                'result': Interview.RESULT_PENDING,
                'result_notes': '',
                'final_result': Interview.FINAL_NONE,
                'final_notes': '',
                'final_by': None,
                'final_at': None,
            },
        )
        interview.interviewers.set(interviewers)

    if to_status == C.STATUS_OFFERED:
        interview = candidate.interview_or_none
        if not interview or not interview.is_approved:
            if job.skip_director_approval:
                raise RecruitmentError('Chỉ trúng tuyển khi phỏng vấn «Đạt».')
            raise RecruitmentError('Chỉ trúng tuyển khi phỏng vấn «Đạt» và giám đốc đã duyệt «Đạt».')
        JobPosting.objects.select_for_update().filter(pk=job.pk).first()
        if filled_count(job, exclude_candidate_id=candidate.pk) >= job.quantity:
            raise RecruitmentError(f'Vị trí đã đủ chỉ tiêu ({job.quantity}).')

    candidate.status = to_status
    candidate.status_changed_at = timezone.now()
    fields = ['status', 'status_changed_at']
    if to_status in REASON_REQUIRED:
        candidate.reject_reason = reason
        fields.append('reject_reason')
    elif to_status in (C.STATUS_REVIEWING, C.STATUS_NEW) and from_status in REASON_REQUIRED:
        candidate.reject_reason = ''
        fields.append('reject_reason')
    candidate.save(update_fields=fields)
    if to_status == C.STATUS_REJECTED and test_mode_enabled():
        _cancel_pending_director(candidate, actor=actor)

    message = reason
    if to_status == C.STATUS_INTERVIEWING:
        interview = candidate.interview
        message = f'Lịch PV: {interview.time_range_label} ({interview.duration_label})'
        if location:
            message += f' · {location.strip()}'
    _log(candidate, CandidateEvent.KIND_STATUS, actor=actor, message=message,
         from_status=from_status, to_status=to_status)
    return candidate


@transaction.atomic
def reschedule_interview(interview, *, actor, interview_time, interview_end, location: str = '') -> Interview:
    """Đổi giờ / địa điểm buổi PV chưa có kết quả (quyền kiểm tra ở view)."""
    interview = Interview.objects.select_for_update().select_related('candidate').get(pk=interview.pk)
    candidate = interview.candidate
    if candidate.status != C.STATUS_INTERVIEWING or interview.result != Interview.RESULT_PENDING:
        raise RecruitmentError('Chỉ cập nhật được buổi phỏng vấn chưa có kết quả.')
    validate_interview_slot(interview_time, interview_end)
    location = (location or '').strip()
    old_label, old_location = interview.time_range_label, interview.location
    interview.interview_time = interview_time
    interview.end_time = interview_end
    interview.location = location
    interview.save(update_fields=['interview_time', 'end_time', 'location'])
    if (old_label, old_location) == (interview.time_range_label, location):
        return interview
    message = f'Đổi lịch PV: {old_label} → {interview.time_range_label} ({interview.duration_label})'
    if location != old_location:
        message += f' · Địa điểm: {location or "—"}'
    _log(candidate, CandidateEvent.KIND_INTERVIEW, actor=actor, message=message)
    return interview


@dataclass
class InterviewOutcome:
    candidate: Candidate
    result: str
    auto_status: str | None
    message: str


def _offer_if_quota(candidate, *, actor, reason: str, via: str = 'Đạt') -> InterviewOutcome:
    """Đã đủ điều kiện trúng tuyển → chuyển nếu còn chỉ tiêu, không thì giữ ở Phỏng vấn."""
    name = candidate.full_name
    job = candidate.job_posting
    JobPosting.objects.select_for_update().filter(pk=job.pk).first()
    if filled_count(job, exclude_candidate_id=candidate.pk) >= job.quantity:
        _log(candidate, CandidateEvent.KIND_NOTE, actor=actor,
             message=f'Đạt nhưng vị trí đã đủ chỉ tiêu ({job.quantity}) — chờ HR xử lý.')
        return InterviewOutcome(
            candidate, Interview.RESULT_PASS, None,
            f'{name}: {via}, nhưng vị trí đã đủ chỉ tiêu ({job.quantity}) — giữ ở bước Phỏng vấn, '
            f'HR tăng chỉ tiêu hoặc xử lý thủ công.',
        )
    transition(candidate, C.STATUS_OFFERED, actor=actor, reason=reason)
    candidate.refresh_from_db()
    return InterviewOutcome(
        candidate, Interview.RESULT_PASS, C.STATUS_OFFERED,
        f'{name}: {via} — đã chuyển sang «Trúng tuyển».',
    )


@transaction.atomic
def record_interview_result(candidate, result: str, notes: str, *, actor, check_permission=True) -> InterviewOutcome:
    """Cấp 1 — lưu kết quả PV.

    Đạt → chờ giám đốc duyệt, trừ vị trí «Bỏ qua giám đốc duyệt» thì chuyển thẳng Trúng tuyển.
    Không đạt → tự chuyển Loại.
    """
    from .permissions import can_record_interview_result

    candidate = Candidate.objects.select_for_update().select_related('job_posting').get(pk=candidate.pk)
    if candidate.status != C.STATUS_INTERVIEWING:
        raise RecruitmentError('Chỉ nhập kết quả khi ứng viên đang ở bước Phỏng vấn.')
    interview = candidate.interview_or_none
    if not interview:
        raise RecruitmentError('Ứng viên chưa có lịch phỏng vấn.')
    if interview.result != Interview.RESULT_PENDING:
        raise RecruitmentError('Buổi phỏng vấn đã có kết quả.')
    if check_permission and not can_record_interview_result(actor, candidate):
        raise RecruitmentError('Bạn không được nhập kết quả phỏng vấn này (không phải người phỏng vấn / quản lý phụ trách).')
    if result not in (Interview.RESULT_PASS, Interview.RESULT_FAIL):
        raise RecruitmentError('Kết quả phỏng vấn không hợp lệ.')
    notes = (notes or '').strip()
    if result == Interview.RESULT_FAIL and not notes:
        raise RecruitmentError('Cần nhận xét khi kết quả «Không đạt».')
    if interview.interview_time > timezone.now():
        raise RecruitmentError('Chưa tới giờ phỏng vấn.')

    interview.result = result
    interview.result_notes = notes
    skip_director = result == Interview.RESULT_PASS and candidate.job_posting.skip_director_approval
    if result == Interview.RESULT_FAIL:
        interview.final_result = Interview.FINAL_NONE
    elif skip_director:
        interview.final_result = Interview.FINAL_SKIPPED
        interview.final_by = None
        interview.final_notes = ''
        interview.final_at = timezone.now()
    else:
        interview.final_result = Interview.FINAL_PENDING
    update_fields = ['result', 'result_notes', 'final_result']
    if skip_director:
        update_fields += ['final_by', 'final_notes', 'final_at']
    interview.save(update_fields=update_fields)
    label = dict(Interview.RESULT_CHOICES)[result]
    log_message = f'Kết quả: {label}' + (f' — {notes}' if notes else '')
    if skip_director:
        log_message += ' — bỏ qua giám đốc duyệt'
    _log(candidate, CandidateEvent.KIND_INTERVIEW, actor=actor, message=log_message)

    name = candidate.full_name
    if result == Interview.RESULT_FAIL:
        transition(candidate, C.STATUS_REJECTED, actor=actor, reason=f'Không đạt phỏng vấn: {notes}')
        candidate.refresh_from_db()
        return InterviewOutcome(candidate, result, C.STATUS_REJECTED, f'{name}: Không đạt — đã tự chuyển sang «Loại».')
    if skip_director:
        return _offer_if_quota(
            candidate, actor=actor,
            reason='Tự động: phỏng vấn Đạt, bỏ qua giám đốc duyệt.',
            via='Đạt — bỏ qua giám đốc duyệt',
        )
    return InterviewOutcome(candidate, result, None, f'{name}: Đạt — chờ giám đốc duyệt.')


@transaction.atomic
def record_final_decision(candidate, decision: str, notes: str, *, actor, check_permission=True) -> InterviewOutcome:
    """Cấp 2 — giám đốc duyệt: Đạt → Trúng tuyển (nếu còn chỉ tiêu), Không đạt → Loại.

    Giám đốc đã phỏng vấn (nhập cấp 1) vẫn phải duyệt riêng ở cấp 2.
    """
    from .permissions import can_final_approve

    candidate = Candidate.objects.select_for_update().select_related('job_posting').get(pk=candidate.pk)
    interview = candidate.interview_or_none
    if candidate.status != C.STATUS_INTERVIEWING or not interview or not interview.awaiting_final:
        raise RecruitmentError('Hồ sơ không ở bước chờ giám đốc duyệt.')
    if check_permission and not can_final_approve(actor):
        raise RecruitmentError('Bạn không có quyền duyệt cấp 2.')
    if decision not in (Interview.FINAL_PASS, Interview.FINAL_FAIL):
        raise RecruitmentError('Kết luận duyệt không hợp lệ.')
    notes = (notes or '').strip()
    if decision == Interview.FINAL_FAIL and not notes:
        raise RecruitmentError('Cần nhận xét khi duyệt «Không đạt».')

    interview.final_result = decision
    interview.final_notes = notes
    interview.final_by = actor
    interview.final_at = timezone.now()
    interview.save(update_fields=['final_result', 'final_notes', 'final_by', 'final_at'])
    label = 'Đạt' if decision == Interview.FINAL_PASS else 'Không đạt'
    _log(candidate, CandidateEvent.KIND_INTERVIEW, actor=actor,
         message=f'Giám đốc duyệt: {label}' + (f' — {notes}' if notes else ''))

    name = candidate.full_name
    if decision == Interview.FINAL_FAIL:
        transition(candidate, C.STATUS_REJECTED, actor=actor, reason=f'Giám đốc duyệt không đạt: {notes}')
        candidate.refresh_from_db()
        return InterviewOutcome(candidate, decision, C.STATUS_REJECTED, f'{name}: Không đạt — đã chuyển sang «Loại».')

    return _offer_if_quota(candidate, actor=actor, reason='Tự động: giám đốc duyệt Đạt.')


@transaction.atomic
def release_director_approvals(job, *, actor) -> int:
    """Vị trí vừa bật «Bỏ qua giám đốc duyệt»: hồ sơ đang chờ duyệt được xử lý như Đạt cấp 2."""
    pending_ids = list(
        Candidate.objects.filter(
            job_posting=job,
            status=C.STATUS_INTERVIEWING,
            interview__result=Interview.RESULT_PASS,
            interview__final_result=Interview.FINAL_PENDING,
        ).values_list('pk', flat=True)
    )
    pending = list(
        Candidate.objects.select_for_update()
        .filter(pk__in=pending_ids)
        .select_related('job_posting')
    )
    for candidate in pending:
        interview = candidate.interview
        interview.final_result = Interview.FINAL_SKIPPED
        interview.final_notes = ''
        interview.final_by = None
        interview.final_at = timezone.now()
        interview.save(update_fields=['final_result', 'final_notes', 'final_by', 'final_at'])
        _log(candidate, CandidateEvent.KIND_INTERVIEW, actor=actor,
             message='Bỏ qua giám đốc duyệt (theo vị trí tuyển dụng).')
        _offer_if_quota(candidate, actor=actor, reason='Tự động: bỏ qua giám đốc duyệt.', via='Đạt — bỏ qua giám đốc duyệt')
    return len(pending)


@transaction.atomic
def restore_director_approvals(job, *, actor) -> int:
    """Tắt «Bỏ qua giám đốc duyệt»: hồ sơ đã bỏ qua nhưng chưa nhận việc phải chờ giám đốc lại.

    Đã nhận việc, loại, hoặc không nhận việc thì giữ nguyên.
    """
    ids = list(
        Candidate.objects.filter(
            job_posting=job,
            status__in=(C.STATUS_INTERVIEWING, C.STATUS_OFFERED),
            interview__result=Interview.RESULT_PASS,
            interview__final_result=Interview.FINAL_SKIPPED,
        ).values_list('pk', flat=True)
    )
    count = 0
    for candidate in _lock_candidates(ids):
        interview = candidate.interview_or_none
        if not interview or interview.final_result != Interview.FINAL_SKIPPED:
            continue
        interview.final_result = Interview.FINAL_PENDING
        interview.final_notes = ''
        interview.final_by = None
        interview.final_at = None
        interview.save(update_fields=['final_result', 'final_notes', 'final_by', 'final_at'])
        _log(candidate, CandidateEvent.KIND_INTERVIEW, actor=actor,
             message='Vị trí yêu cầu giám đốc duyệt lại.')
        if candidate.status == C.STATUS_OFFERED:
            _set_status(
                candidate, C.STATUS_INTERVIEWING, actor=actor,
                message='Yêu cầu giám đốc duyệt lại — chuyển về Phỏng vấn.',
            )
        count += 1
    return count


def sync_skip_director_approval(job, *, actor) -> int:
    if job.skip_director_approval:
        return release_director_approvals(job, actor=actor)
    return restore_director_approvals(job, actor=actor)


@transaction.atomic
def release_cv_reviews(job, *, actor) -> int:
    """Bật «Bỏ qua duyệt CV»: hồ sơ đang chờ quản lý đánh giá về Mới để HR lên lịch phỏng vấn."""
    ids = list(
        Candidate.objects.filter(job_posting=job, status=C.STATUS_REVIEWING).values_list('pk', flat=True)
    )
    count = 0
    for candidate in _lock_candidates(ids):
        if candidate.status != C.STATUS_REVIEWING:
            continue
        _set_status(
            candidate, C.STATUS_NEW, actor=actor,
            message='Bỏ qua duyệt CV — đưa về Mới để lên lịch phỏng vấn.',
        )
        count += 1
    return count


@transaction.atomic
def restore_cv_reviews(job, *, actor) -> int:
    """Tắt «Bỏ qua duyệt CV»: buổi PV chưa có kết quả và chưa được duyệt CV thì hủy lịch, chờ quản lý đánh giá.

    Hồ sơ đã có kết quả phỏng vấn, đã trúng tuyển hoặc đã nhận việc giữ nguyên.
    """
    recommended = CandidateReview.objects.filter(
        candidate__job_posting=job,
        decision=CandidateReview.DECISION_RECOMMEND,
    ).values('candidate_id')
    ids = list(
        Candidate.objects.filter(
            job_posting=job,
            status=C.STATUS_INTERVIEWING,
            interview__result=Interview.RESULT_PENDING,
        ).exclude(pk__in=recommended).values_list('pk', flat=True)
    )
    target = C.STATUS_REVIEWING if job.target_department_id else C.STATUS_NEW
    count = 0
    for candidate in _lock_candidates(ids):
        interview = candidate.interview_or_none
        if candidate.status != C.STATUS_INTERVIEWING or not interview or interview.result != Interview.RESULT_PENDING:
            continue
        if has_recommend_review(candidate):
            continue
        when = interview.time_range_label
        interview.delete()
        if target == C.STATUS_REVIEWING:
            message = f'Yêu cầu duyệt CV — hủy lịch PV {when}, chuyển về chờ quản lý đánh giá.'
        else:
            message = f'Yêu cầu duyệt CV — hủy lịch PV {when}. Vị trí chưa gắn phòng ban nên đưa về Mới.'
        _set_status(candidate, target, actor=actor, message=message)
        count += 1
    return count


def sync_skip_cv_review(job, *, actor) -> int:
    if job.skip_cv_review:
        return release_cv_reviews(job, actor=actor)
    return restore_cv_reviews(job, actor=actor)


# ---------------------------------------------------------------- manager review

@transaction.atomic
def submit_review(candidate, reviewer, *, decision: str, rating=None, comment: str = '') -> CandidateReview:
    from .permissions import can_review_candidate

    candidate = Candidate.objects.select_for_update().select_related('job_posting').get(pk=candidate.pk)
    if not can_review_candidate(reviewer, candidate):
        raise RecruitmentError('Bạn không thể đánh giá hồ sơ này (ngoài phạm vi hoặc không ở bước đánh giá).')
    if decision not in CandidateReview.ACTIVE_DECISIONS:
        raise RecruitmentError('Kết luận không hợp lệ.')
    comment = (comment or '').strip()
    if decision == CandidateReview.DECISION_NOT_SUITABLE and not comment:
        raise RecruitmentError('Cần nhận xét khi đánh giá «Không đạt».')
    if rating is not None and not 1 <= int(rating) <= 5:
        raise RecruitmentError('Điểm hồ sơ từ 1 đến 5.')

    review, created = CandidateReview.objects.update_or_create(
        candidate=candidate, reviewer=reviewer,
        defaults={'decision': decision, 'rating': rating, 'comment': comment},
    )
    text = review.get_decision_display()
    if rating:
        text += f' · {rating}/5'
    if comment:
        text += f' — {comment}'
    _log(candidate, CandidateEvent.KIND_REVIEW, actor=reviewer,
         message=('' if created else 'Cập nhật: ') + text)
    return review


# ---------------------------------------------------------------- onboard

@dataclass
class OnboardResult:
    user: User
    password: str
    employee_code: str
    course_title: str | None
    permission_group: str | None


def onboarding_course():
    from training.models import Course

    return Course.objects.filter(title__iexact=ONBOARDING_COURSE_TITLE, is_active=True).first()


def onboarding_permission_group():
    """Nhóm quyền mặc định cho NV mới — giống form «Thêm nhân viên» (thử việc → mặc định NV)."""
    from hrm.group_permissions import default_group_for_role
    from hrm.permissions import ROLE_EMPLOYEE
    from PortalJustPlay.utils import get_probation_permission_group

    return get_probation_permission_group() or default_group_for_role(ROLE_EMPLOYEE)


def onboard_candidate(candidate, *, actor, join_date=None, email=None, gender=None,
                      date_of_birth=None) -> OnboardResult:
    """Tạo tài khoản nhân viên. ``email`` / ``gender`` / ``date_of_birth`` (nếu truyền) ghi đè hồ sơ ứng viên."""
    from hrm.models import Profile
    from hrm.permissions import ROLE_EMPLOYEE
    from PortalJustPlay.utils import (
        generate_hm_username,
        generate_secure_password,
        next_employee_code,
    )

    with transaction.atomic():
        candidate = Candidate.objects.select_for_update(of=('self',)).select_related(
            'job_posting', 'job_posting__target_department',
        ).get(pk=candidate.pk)
        if candidate.status != C.STATUS_OFFERED:
            raise RecruitmentError('Chỉ onboard ứng viên đang ở bước «Trúng tuyển».')
        if candidate.employee_id:
            raise RecruitmentError('Ứng viên đã có tài khoản nhân viên.')
        if email is not None:
            candidate.email = email.strip()
        if gender is not None:
            candidate.gender = gender
        if date_of_birth is not None:
            candidate.date_of_birth = date_of_birth
        if candidate.email and User.objects.filter(email__iexact=candidate.email).exists():
            raise RecruitmentError(f'Email {candidate.email} đã thuộc một tài khoản khác.')
        job = candidate.job_posting
        if not job.target_department_id:
            raise RecruitmentError('Vị trí chưa gắn phòng ban — cập nhật vị trí trước khi onboard.')

        username = generate_hm_username(candidate.full_name)
        password = generate_secure_password()
        employee_code = next_employee_code()
        group = onboarding_permission_group()
        try:
            user = User.objects.create_user(
                username=username,
                email=(candidate.email or '').strip(),
                password=password,
                first_name=candidate.full_name,
            )
        except IntegrityError as exc:
            raise RecruitmentError('Trùng tên đăng nhập — thử lại.') from exc

        user.profile, _ = Profile.objects.update_or_create(
            user=user,
            defaults={
                'employee_code': employee_code,
                'full_name': candidate.full_name,
                'phone': candidate.phone,
                'gender': candidate.gender,
                'date_of_birth': candidate.date_of_birth,
                'department': job.target_department,
                'division': job.target_division,
                'job_position': ' '.join((job.position or '').split())[:100],
                'job_title': job.title,
                'join_date': join_date or timezone.localdate(),
                'on_probation': True,
                'role': ROLE_EMPLOYEE,
                'permission_group': group,
                'must_change_password': True,
                'is_employed': True,
            },
        )

        course = onboarding_course()
        if course:
            course.assigned_users.add(user)
            if course.final_exam_id:
                course.final_exam.assigned_users.add(user)

        from_status = candidate.status
        candidate.status = C.STATUS_HIRED
        candidate.employee = user
        candidate.status_changed_at = timezone.now()
        candidate.save(update_fields=[
            'status', 'employee', 'status_changed_at', 'email', 'gender', 'date_of_birth',
        ])
        _log(
            candidate, CandidateEvent.KIND_ONBOARD, actor=actor,
            from_status=from_status, to_status=C.STATUS_HIRED,
            message=(
                f'Tạo tài khoản {username} ({user.email}) · Mã NV {employee_code}'
                + (f' · Nhóm quyền {group.name}' if group else '')
                + (f' · Giao khóa «{course.title}»' if course else ' · Chưa có khóa Đào tạo hội nhập')
            ),
        )

    try:
        from audit.services.password_sync import notify_external_password_changed

        notify_external_password_changed(user, password)
    except Exception:
        logger.exception('Đồng bộ mật khẩu ngoài thất bại (onboard) user=%s', user.pk)

    return OnboardResult(
        user=user,
        password=password,
        employee_code=employee_code,
        course_title=course.title if course else None,
        permission_group=group.name if group else None,
    )


# ================================================================ Thiết lập danh mục

def option_code(model, name: str) -> str:
    """Mã ASCII duy nhất từ tên (lưu vào hồ sơ — không đổi khi đổi tên)."""
    from django.utils.text import slugify

    base = slugify(name.replace('đ', 'd').replace('Đ', 'D')).replace('-', '_')[:16] or 'muc'
    code, n = base, 2
    while model.objects.filter(code=code).exists():
        code = f'{base[:16 - len(str(n)) - 1]}_{n}'
        n += 1
    return code


def option_usage(obj) -> int:
    if isinstance(obj, CandidateSource):
        return Candidate.objects.filter(source=obj.code).count()
    if isinstance(obj, CandidateFileKind):
        from .models import CandidateFile

        return CandidateFile.objects.filter(kind=obj.code).count()
    if isinstance(obj, InterviewLocation):
        return Interview.objects.filter(location=obj.name).count()
    return 0


def _ensure_cv_kind_left(exclude_pk):
    if not CandidateFileKind.objects.filter(is_cv=True, is_active=True).exclude(pk=exclude_pk).exists():
        raise RecruitmentError('Cần ít nhất 1 loại hồ sơ «Là CV» đang dùng.')


def save_option(form):
    """Lưu form danh mục (thêm / sửa). Địa điểm đổi tên → cập nhật lịch PV chưa có kết quả."""
    obj = form.instance
    if isinstance(obj, CandidateFileKind) and obj.pk and 'is_cv' in form.changed_data and not obj.is_cv:
        _ensure_cv_kind_left(obj.pk)
    old_name = type(obj).objects.filter(pk=obj.pk).values_list('name', flat=True).first() if obj.pk else None
    obj = form.save(commit=False)
    if obj.sort_order is None:
        last = type(obj).objects.exclude(pk=obj.pk).order_by('-sort_order').values_list('sort_order', flat=True).first()
        obj.sort_order = (last or 0) + 10
    if hasattr(obj, 'code') and not obj.code:
        obj.code = option_code(type(obj), obj.name)
    obj.save()
    if isinstance(obj, InterviewLocation) and old_name and old_name != obj.name:
        Interview.objects.filter(location=old_name, result=Interview.RESULT_PENDING).update(location=obj.name)
    return obj


def toggle_option(obj):
    if getattr(obj, 'is_system', False) and obj.is_active:
        raise RecruitmentError(f'«{obj.name}» là mục hệ thống — không ngừng dùng được.')
    if isinstance(obj, CandidateFileKind) and obj.is_active and obj.is_cv:
        _ensure_cv_kind_left(obj.pk)
    obj.is_active = not obj.is_active
    obj.save(update_fields=['is_active'])
    return obj


def delete_option(obj):
    if getattr(obj, 'is_system', False):
        raise RecruitmentError(f'«{obj.name}» là mục hệ thống — không xóa được.')
    used = option_usage(obj)
    if used and not isinstance(obj, InterviewLocation):
        raise RecruitmentError(f'«{obj.name}» đang được dùng ở {used} hồ sơ — chỉ ngừng dùng được.')
    if isinstance(obj, CandidateFileKind) and obj.is_cv and obj.is_active:
        _ensure_cv_kind_left(obj.pk)
    name = obj.name
    obj.delete()
    return name
