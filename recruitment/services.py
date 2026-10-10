"""Quy tắc nghiệp vụ Tuyển dụng — mọi thay đổi trạng thái đều đi qua đây.

Luồng ứng viên:
    Mới → Chờ quản lý đánh giá → Phỏng vấn → Trúng tuyển → Đã nhận việc
    (Loại / Không nhận việc bắt buộc lý do; có thể «Mở lại» về bước đánh giá.)
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


def _digits(phone: str) -> str:
    return re.sub(r'\D', '', phone or '')


def status_label(status: str) -> str:
    return dict(C.STATUS_CHOICES).get(status, status)


def allowed_targets(candidate) -> list[str]:
    targets = set(TRANSITIONS.get(candidate.status, ()))
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
    phone_digits = _digits(data.phone)
    if not data.full_name.strip() or len(phone_digits) < 9:
        raise RecruitmentError('Cần họ tên và số điện thoại hợp lệ.')
    for other in job.candidates.only('phone', 'email'):
        if _digits(other.phone) == phone_digits:
            raise RecruitmentError(f'Số điện thoại {data.phone} đã nộp cho vị trí này.')
        if data.email and other.email and other.email.lower() == data.email.lower():
            raise RecruitmentError(f'Email {data.email} đã nộp cho vị trí này.')

    candidate = Candidate.objects.create(
        job_posting=job,
        full_name=data.full_name.strip(),
        gender=data.gender or '',
        date_of_birth=data.date_of_birth,
        phone=data.phone.strip(),
        email=(data.email or '').strip(),
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


def add_note(candidate, message: str, *, actor):
    message = (message or '').strip()
    if not message:
        raise RecruitmentError('Ghi chú trống.')
    return _log(candidate, CandidateEvent.KIND_NOTE, actor=actor, message=message)


INTERVIEW_MIN_MINUTES = 15
INTERVIEW_MAX_MINUTES = 8 * 60


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
               interview_time=None, interview_end=None, location: str = '', interviewers=None) -> Candidate:
    candidate = Candidate.objects.select_for_update().select_related('job_posting').get(pk=candidate.pk)
    from_status = candidate.status
    if to_status == C.STATUS_HIRED:
        raise RecruitmentError('Chuyển sang «Đã nhận việc» bằng thao tác Onboard.')
    if to_status not in TRANSITIONS.get(from_status, ()):
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
        if not has_recommend_review(candidate):
            raise RecruitmentError('Cần ít nhất 1 đánh giá «Đạt» của quản lý.')
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
        interview.interviewers.set(interviewers or [])

    if to_status == C.STATUS_OFFERED:
        interview = candidate.interview_or_none
        if not interview or not interview.is_approved:
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
    elif to_status == C.STATUS_REVIEWING and from_status in REASON_REQUIRED:
        candidate.reject_reason = ''
        fields.append('reject_reason')
    candidate.save(update_fields=fields)

    message = reason
    if to_status == C.STATUS_INTERVIEWING:
        interview = candidate.interview
        message = f'Lịch PV: {interview.time_range_label} ({interview.duration_label})'
        if location:
            message += f' · {location.strip()}'
    _log(candidate, CandidateEvent.KIND_STATUS, actor=actor, message=message,
         from_status=from_status, to_status=to_status)
    return candidate


@dataclass
class InterviewOutcome:
    candidate: Candidate
    result: str
    auto_status: str | None
    message: str


@transaction.atomic
def record_interview_result(candidate, result: str, notes: str, *, actor, check_permission=True) -> InterviewOutcome:
    """Cấp 1 — lưu kết quả PV: Đạt → chờ giám đốc duyệt, Không đạt → tự chuyển Loại."""
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
    interview.final_result = Interview.FINAL_PENDING if result == Interview.RESULT_PASS else Interview.FINAL_NONE
    interview.save(update_fields=['result', 'result_notes', 'final_result'])
    label = dict(Interview.RESULT_CHOICES)[result]
    _log(candidate, CandidateEvent.KIND_INTERVIEW, actor=actor,
         message=f'Kết quả: {label}' + (f' — {notes}' if notes else ''))

    name = candidate.full_name
    if result == Interview.RESULT_FAIL:
        transition(candidate, C.STATUS_REJECTED, actor=actor, reason=f'Không đạt phỏng vấn: {notes}')
        candidate.refresh_from_db()
        return InterviewOutcome(candidate, result, C.STATUS_REJECTED, f'{name}: Không đạt — đã tự chuyển sang «Loại».')
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

    job = candidate.job_posting
    JobPosting.objects.select_for_update().filter(pk=job.pk).first()
    if filled_count(job, exclude_candidate_id=candidate.pk) >= job.quantity:
        _log(candidate, CandidateEvent.KIND_NOTE, actor=actor,
             message=f'Đạt nhưng vị trí đã đủ chỉ tiêu ({job.quantity}) — chờ HR xử lý.')
        return InterviewOutcome(
            candidate, decision, None,
            f'{name}: Đạt, nhưng vị trí đã đủ chỉ tiêu ({job.quantity}) — giữ ở bước Phỏng vấn, '
            f'HR tăng chỉ tiêu hoặc xử lý thủ công.',
        )
    transition(candidate, C.STATUS_OFFERED, actor=actor, reason='Tự động: giám đốc duyệt Đạt.')
    candidate.refresh_from_db()
    return InterviewOutcome(candidate, decision, C.STATUS_OFFERED, f'{name}: Đạt — đã chuyển sang «Trúng tuyển».')


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


def suggest_email(full_name: str) -> str:
    """Email công ty gợi ý theo họ tên (tên.họ@justplay.vn) — cùng quy tắc form Thêm nhân viên."""
    from PortalJustPlay.utils import generate_hm_email, generate_hm_username

    full_name = (full_name or '').strip()
    return generate_hm_email(generate_hm_username(full_name)) if full_name else ''


def onboard_candidate(candidate, *, actor, join_date=None, email=None, gender=None,
                      date_of_birth=None) -> OnboardResult:
    """Tạo tài khoản nhân viên. ``email`` / ``gender`` / ``date_of_birth`` (nếu truyền) ghi đè hồ sơ ứng viên."""
    from hrm.models import Profile
    from hrm.permissions import ROLE_EMPLOYEE
    from PortalJustPlay.utils import (
        generate_hm_email,
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
                email=candidate.email or generate_hm_email(username),
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
