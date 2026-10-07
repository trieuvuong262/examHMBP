"""Tuyển dụng — view mỏng; quy tắc nghiệp vụ nằm ở ``recruitment.services``."""

from datetime import datetime, timedelta
from functools import wraps

import openpyxl
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import (
    Case,
    Count,
    Exists,
    F,
    IntegerField,
    Max,
    OuterRef,
    Prefetch,
    Q,
    Value,
    When,
)
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_RECRUITMENT, user_can_access_module
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_columns, paginate_queryset
from utilities.date_range_filter import (
    date_range_span_context,
    parse_date_range_span_from_request,
)

from . import services
from .forms import (
    CandidateFileForm,
    CandidateFileKindForm,
    CandidateForm,
    CandidateSourceForm,
    InterviewLocationForm,
    InterviewResultForm,
    JobPostingForm,
    OnboardForm,
    ReviewForm,
    TransitionForm,
)
from .models import (
    Candidate,
    CandidateEvent,
    CandidateFile,
    CandidateFileKind,
    CandidateReview,
    CandidateSource,
    Interview,
    InterviewLocation,
    JobPosting,
)
from .permissions import (
    can_candidates,
    can_jobs,
    can_onboard,
    can_record_interview_result,
    can_review_candidate,
    can_settings,
    can_view_candidate,
    interview_queue,
    is_hiring_manager,
    is_interviewer,
    manager_can_access_job,
    manager_job_filter,
    scope_label,
    visible_jobs_q,
    visible_scope,
)

C = Candidate

KANBAN_COLUMNS = [
    (C.STATUS_NEW, 'Mới', 'is-new'),
    (C.STATUS_REVIEWING, 'Chờ đánh giá', 'is-reviewing'),
    (C.STATUS_INTERVIEWING, 'Phỏng vấn', 'is-interviewing'),
    (C.STATUS_OFFERED, 'Trúng tuyển', 'is-offered'),
    (C.STATUS_HIRED, 'Đã nhận việc', 'is-hired'),
    (C.STATUS_NOT_ONBOARDED, 'Không nhận việc', 'is-closed'),
    (C.STATUS_REJECTED, 'Loại', 'is-closed'),
]
# Kanban chỉ cho luồng đang xử lý + 2 cột kết thúc có thể thả vào.
# «Đã nhận việc» là trạng thái cuối — xem ở tab Danh sách.
KANBAN_BOARD_STATUSES = (
    C.STATUS_NEW, C.STATUS_REVIEWING, C.STATUS_INTERVIEWING, C.STATUS_OFFERED,
    C.STATUS_NOT_ONBOARDED, C.STATUS_REJECTED,
)
KANBAN_PAGE_SIZE = 20

# Nhóm lọc nhanh trên tab Danh sách.
STATUS_GROUPS = {
    'dang-xu-ly': ('Đang xử lý', (C.STATUS_NEW, C.STATUS_REVIEWING, C.STATUS_INTERVIEWING, C.STATUS_OFFERED)),
    'ket-thuc': ('Loại / Không nhận việc', (C.STATUS_REJECTED, C.STATUS_NOT_ONBOARDED)),
}
JOB_STATUS_ORDER = (
    JobPosting.STATUS_OPEN, JobPosting.STATUS_DRAFT, JobPosting.STATUS_PAUSED, JobPosting.STATUS_CLOSED,
)
JOB_ACTION_LABELS = {
    JobPosting.STATUS_PAUSED: 'Tạm dừng tuyển',
    JobPosting.STATUS_CLOSED: 'Đóng vị trí',
}
REVIEW_DECISION_UI = {
    CandidateReview.DECISION_RECOMMEND: ('is-pass', 'bi-check-circle-fill'),
    CandidateReview.DECISION_NOT_SUITABLE: ('is-fail', 'bi-x-circle-fill'),
}
JOB_ATTENTION = 'can-chu-y'
JOB_DEADLINE_SOON_DAYS = 7

CANDIDATE_SORTS = {
    'moi-nhat': ('Nộp mới nhất', ('-applied_at', '-id')),
    'cu-nhat': ('Nộp cũ nhất', ('applied_at', 'id')),
    'cap-nhat': ('Cập nhật gần nhất', ('-status_changed_at', '-id')),
    'ten': ('Họ tên A–Z', ('full_name', 'id')),
}


def _fail(request, exc, fallback):
    messages.error(request, str(exc))
    return redirect(fallback)


def _manager_required(view_func):
    """Trưởng bộ phận / Trưởng phòng / Giám đốc."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not is_hiring_manager(request.user):
            messages.error(request, 'Chức năng dành cho Trưởng bộ phận, Trưởng phòng và Giám đốc.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _reviewer_required(view_func):
    """Quản lý tuyển dụng hoặc người đang được giao phỏng vấn ứng viên."""
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not (is_hiring_manager(request.user) or interview_queue(request.user).exists()):
            messages.error(request, 'Chức năng dành cho quản lý và người được giao phỏng vấn.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _candidate_qs():
    return Candidate.objects.select_related(
        'job_posting', 'job_posting__target_department', 'job_posting__target_division',
        'referred_by__profile', 'employee',
    ).prefetch_related('files')


# --- Phạm vi dữ liệu: mọi màn hình HR chỉ thấy vị trí / ứng viên trong phạm vi của user ---

def _jobs(request):
    return JobPosting.objects.filter(visible_jobs_q(request.user))


def _cands(request):
    return _candidate_qs().filter(visible_jobs_q(request.user, 'job_posting__'))


def _interviews(request):
    return Interview.objects.filter(visible_jobs_q(request.user, 'candidate__job_posting__'))


def _get_candidate(request, pk):
    return get_object_or_404(_cands(request), pk=pk)


def _open_jobs():
    today = timezone.localdate()
    return (
        JobPosting.objects.filter(status=JobPosting.STATUS_OPEN)
        .filter(Q(deadline__isnull=True) | Q(deadline__gte=today))
        .select_related('target_department', 'target_division')
        .order_by('title')
    )


# ================================================================ Tổng quan

@login_required
def recruitment_overview(request):
    if not user_can_access_module(request.user, MODULE_RECRUITMENT):
        messages.error(request, 'Bạn không có quyền xem Tuyển dụng.')
        return redirect('home_portal')
    now = timezone.now()
    today = timezone.localdate()
    scope_q = visible_jobs_q(request.user, 'job_posting__')
    status_counts = dict(
        Candidate.objects.filter(scope_q).values_list('status').annotate(n=Count('id')).values_list('status', 'n')
    )
    pending_results = (
        _interviews(request).filter(
            candidate__status=C.STATUS_INTERVIEWING, result=Interview.RESULT_PENDING, interview_time__lte=now,
        ).select_related('candidate', 'candidate__job_posting').order_by('interview_time')[:10]
    )
    upcoming = (
        _interviews(request).filter(
            candidate__status=C.STATUS_INTERVIEWING, interview_time__gt=now,
            interview_time__lt=now + timedelta(days=7),
        ).select_related('candidate', 'candidate__job_posting').order_by('interview_time')[:10]
    )
    awaiting_onboard = _cands(request).filter(status=C.STATUS_OFFERED).order_by('status_changed_at')[:10]
    draft_jobs = (
        _jobs(request).filter(status=JobPosting.STATUS_DRAFT)
        .select_related('target_department', 'target_division', 'service_request').order_by('-created_at')[:10]
    )
    return render(request, 'recruitment/admin/overview.html', {
        'open_jobs_count': _open_jobs().filter(visible_jobs_q(request.user)).count(),
        'draft_jobs': draft_jobs,
        'status_counts': [(key, label, status_counts.get(key, 0)) for key, label, _ in KANBAN_COLUMNS],
        'pending_results': pending_results,
        'upcoming': upcoming,
        'awaiting_onboard': awaiting_onboard,
        'hired_this_month': Candidate.objects.filter(scope_q).filter(
            status=C.STATUS_HIRED, status_changed_at__year=today.year, status_changed_at__month=today.month,
        ).count(),
        'scope_label': scope_label(request.user),
        'can_candidates_view': can_candidates(request.user, 'view'),
        'can_jobs_view': can_jobs(request.user, 'view'),
    })


# ================================================================ Vị trí tuyển dụng

@module_perm_required(MODULE_RECRUITMENT, 'view')
def job_posting_list(request):
    search_query = get_search_query(request)
    status = (request.GET.get('status') or '').strip()
    dept = (request.GET.get('department') or '').strip()
    today = timezone.localdate()
    base = services.annotate_job_counts(
        _jobs(request).select_related('target_department', 'target_division', 'service_request')
    )
    if dept.isdigit():
        base = base.filter(target_department_id=int(dept))
    base = apply_term_search(
        base, search_query, 'title__icontains', 'target_department__name__icontains',
        'department__icontains', 'position__icontains',
    )
    attention_q = Q(status=JobPosting.STATUS_OPEN) & (
        Q(deadline__lte=today + timedelta(days=JOB_DEADLINE_SOON_DAYS)) | Q(n_filled__gte=F('quantity'))
    )
    status_counts = dict(base.order_by().values_list('status').annotate(n=Count('id', distinct=True)))
    qs = base
    if status == JOB_ATTENTION:
        qs = qs.filter(attention_q)
    elif status in dict(JobPosting.STATUS_CHOICES):
        qs = qs.filter(status=status)
    qs = qs.annotate(
        status_rank=Case(
            *[When(status=s, then=Value(i)) for i, s in enumerate(JOB_STATUS_ORDER)],
            default=Value(len(JOB_STATUS_ORDER)), output_field=IntegerField(),
        ),
    ).order_by('status_rank', F('deadline').asc(nulls_last=True), '-created_at')
    page_obj, query_string = paginate_queryset(request, qs)

    can_update = can_jobs(request.user, 'update')
    jobs = list(page_obj.object_list)
    for job in jobs:
        _decorate_job_row(job, today, can_update)

    open_rows = list(base.filter(status=JobPosting.STATUS_OPEN).values_list('quantity', 'n_filled', 'n_active'))
    chip_url = _query_url(request, status=None, page=None)
    chips = [{'key': '', 'label': 'Tất cả', 'count': sum(status_counts.values()), 'tone': 'all'}]
    if status_counts.get(JobPosting.STATUS_OPEN):
        chips.append({'key': JOB_ATTENTION, 'label': 'Cần chú ý', 'count': base.filter(attention_q).count(), 'tone': 'need'})
    chips += [
        {'key': s, 'label': dict(JobPosting.STATUS_CHOICES)[s], 'count': status_counts.get(s, 0), 'tone': s}
        for s in JOB_STATUS_ORDER
    ]
    for chip in chips:
        chip['active'] = status == chip['key']
        chip['url'] = chip_url + (f'&status={chip["key"]}' if chip['key'] else '')
    from hrm.models import Department

    return render(request, 'recruitment/admin/job_posting_list.html', {
        'jobs': jobs,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'status_filter': status,
        'department_filter': dept,
        'status_chips': chips,
        'summary': {
            'open': len(open_rows),
            'missing': sum(max(quota - filled, 0) for quota, filled, _ in open_rows),
            'active': sum(active for *_, active in open_rows),
        },
        'departments': Department.objects.filter(job_postings__in=_jobs(request)).distinct().order_by('sort_order', 'name'),
        'scope_label': scope_label(request.user),
        'can_create': can_jobs(request.user, 'create'),
        'can_update': can_update,
        'can_add_candidate': can_candidates(request.user, 'create'),
    })


def _query_url(request, **overrides) -> str:
    """URL hiện tại với một số tham số GET được thay / bỏ (giá trị None)."""
    params = request.GET.copy()
    for key, value in overrides.items():
        params.pop(key, None)
        if value is not None:
            params[key] = value
    return f'{request.path}?{params.urlencode()}'


def _decorate_job_row(job, today, can_update):
    """Gắn số liệu hiển thị + thao tác hợp lệ theo JOB_TRANSITIONS cho 1 dòng vị trí."""
    job.fill_pct = min(100, round(job.n_filled * 100 / job.quantity)) if job.quantity else 0
    job.is_full = bool(job.quantity) and job.n_filled >= job.quantity
    job.days_left = (job.deadline - today).days if job.deadline else None
    live = job.status in (JobPosting.STATUS_OPEN, JobPosting.STATUS_PAUSED, JobPosting.STATUS_DRAFT)
    job.deadline_tone, job.deadline_note = '', ''
    if live and job.days_left is not None:
        if job.days_left < 0:
            job.deadline_tone, job.deadline_note = 'expired', f'Quá hạn {-job.days_left} ngày'
        elif job.days_left == 0:
            job.deadline_tone, job.deadline_note = 'soon', 'Hết hạn hôm nay'
        elif job.days_left <= JOB_DEADLINE_SOON_DAYS:
            job.deadline_tone, job.deadline_note = 'soon', f'Còn {job.days_left} ngày'
    job.candidates_url = (
        reverse('candidate_list') if job.status == JobPosting.STATUS_OPEN else reverse('kanban_board')
    ) + f'?job_id={job.pk}'
    job.open_blocker = services.open_blocker(job)
    targets = services.JOB_TRANSITIONS.get(job.status, set()) if can_update else set()
    can_open = JobPosting.STATUS_OPEN in targets and not job.open_blocker
    open_label = 'Mở tuyển' if job.status == JobPosting.STATUS_DRAFT else 'Mở lại'
    job.status_actions = [
        (s, open_label if s == JobPosting.STATUS_OPEN else JOB_ACTION_LABELS[s])
        for s in JOB_STATUS_ORDER
        if s in targets and (s != JobPosting.STATUS_OPEN or can_open)
    ]
    job.primary_open_label = open_label if can_open and job.status != JobPosting.STATUS_CLOSED else ''
    job.needs_completion = (
        JobPosting.STATUS_OPEN in targets and bool(job.open_blocker) and job.status != JobPosting.STATUS_CLOSED
    )


@module_perm_required(MODULE_RECRUITMENT, 'create')
def job_posting_create(request):
    form = JobPostingForm(request.POST or None, scope=visible_scope(request.user))
    if request.method == 'POST' and form.is_valid():
        job = form.save(commit=False)
        job.created_by = request.user
        job.status = JobPosting.STATUS_DRAFT
        job.save()
        messages.success(request, f'Đã tạo vị trí «{job.title}» ở trạng thái Nháp.')
        return redirect('job_posting_edit', pk=job.pk)
    return render(request, 'recruitment/admin/job_posting_form.html', {
        'form': form, 'title': 'Tạo vị trí tuyển dụng',
    })


@module_perm_required(MODULE_RECRUITMENT, 'update')
def job_posting_edit(request, pk):
    job = get_object_or_404(_jobs(request).select_related('service_request'), pk=pk)
    form = JobPostingForm(request.POST or None, instance=job, scope=visible_scope(request.user))
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Đã cập nhật vị trí tuyển dụng.')
        return redirect('job_posting_edit', pk=job.pk)
    return render(request, 'recruitment/admin/job_posting_form.html', {
        'form': form,
        'title': job.title,
        'job': job,
        'job_actions': [
            (s, label) for s, label in JobPosting.STATUS_CHOICES
            if s in services.JOB_TRANSITIONS.get(job.status, set())
        ],
        'filled': services.filled_count(job),
        'candidate_count': job.candidates.count(),
        'can_delete': can_jobs(request.user, 'delete'),
    })


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def job_posting_status(request, pk):
    job = get_object_or_404(_jobs(request), pk=pk)
    try:
        services.change_job_status(job, request.POST.get('status', ''), actor=request.user)
        messages.success(request, f'Vị trí «{job.title}»: {job.get_status_display()}.')
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    return redirect(_safe_next(request, reverse('job_posting_edit', args=[job.pk])))


@module_perm_required(MODULE_RECRUITMENT, 'delete')
@require_POST
def job_posting_delete(request, pk):
    job = get_object_or_404(_jobs(request), pk=pk)
    title = job.title
    try:
        services.delete_job(job)
    except services.RecruitmentError as exc:
        return _fail(request, exc, reverse('job_posting_edit', args=[pk]))
    messages.success(request, f'Đã xóa vị trí «{title}».')
    return redirect('job_posting_list')


# ================================================================ Ứng viên — Danh sách & Kanban

def _candidate_filters(request):
    """Bộ lọc dùng chung cho tab Danh sách / Kanban / xuất Excel."""
    return {
        'q': get_search_query(request),
        'job_id': (request.GET.get('job_id') or '').strip(),
        'status': (request.GET.get('status') or '').strip(),
        'source': (request.GET.get('source') or '').strip(),
        'sort': (request.GET.get('sort') or '').strip(),
    }


def _filtered_candidates(request, f, *, include_closed_jobs=False, open_jobs_only=False):
    qs = _cands(request).annotate(
        n_recommend=Count('reviews', filter=Q(reviews__decision=CandidateReview.DECISION_RECOMMEND), distinct=True),
        n_reviews=Count('reviews', distinct=True),
    ).select_related('interview')
    if open_jobs_only:
        qs = qs.filter(job_posting__status=JobPosting.STATUS_OPEN)
    if f['job_id'].isdigit():
        qs = qs.filter(job_posting_id=int(f['job_id']))
    elif not include_closed_jobs:
        qs = qs.exclude(job_posting__status=JobPosting.STATUS_CLOSED)
    if f['source']:
        qs = qs.filter(source=f['source'])
    return apply_term_search(qs, f['q'], 'full_name__icontains', 'phone__icontains', 'email__icontains')


def _view_tabs(request, current):
    """Tab Danh sách | Kanban — giữ bộ lọc vị trí + tìm kiếm khi chuyển tab."""
    keep = {k: v for k, v in request.GET.items() if k in ('job_id', 'q') and v}
    from urllib.parse import urlencode

    suffix = f'?{urlencode(keep)}' if keep else ''
    return [
        {'key': 'list', 'label': 'Danh sách', 'icon': 'bi-list-ul',
         'url': reverse('candidate_list') + suffix, 'active': current == 'list'},
        {'key': 'kanban', 'label': 'Kanban', 'icon': 'bi-kanban',
         'url': reverse('kanban_board') + suffix, 'active': current == 'kanban'},
    ]


def _interview_locations():
    return list(InterviewLocation.objects.filter(is_active=True).values('name', 'note'))


def _attach_move_targets(candidates):
    """Gắn danh sách bước được chuyển (nút «Chuyển») — «Đã nhận việc» chỉ qua Onboard."""
    for cand in candidates:
        cand.move_targets = [(s, services.status_label(s)) for s in services.allowed_targets(cand)]
    return candidates


def _candidate_page_context(request, current, f):
    return {
        'view_tabs': _view_tabs(request, current),
        'filters': f,
        'search_query': f['q'],
        'jobs': _jobs(request).exclude(status=JobPosting.STATUS_DRAFT).order_by('title'),
        'selected_job': int(f['job_id']) if f['job_id'].isdigit() else None,
        'can_create': can_candidates(request.user, 'create'),
        'can_move': can_candidates(request.user, 'update'),
        'can_export': can_candidates(request.user, 'export'),
        'transitions': {k: sorted(v) for k, v in services.TRANSITIONS.items()},
        'status_labels': dict(C.STATUS_CHOICES),
        'transition_form': TransitionForm(),
        'interview_locations': _interview_locations(),
        'scope_label': scope_label(request.user),
    }


NEED_ACTION = 'can-xu-ly'
PIPELINE_STEPS = [
    (C.STATUS_NEW, 'Mới'),
    (C.STATUS_REVIEWING, 'Đánh giá'),
    (C.STATUS_INTERVIEWING, 'Phỏng vấn'),
    (C.STATUS_OFFERED, 'Trúng tuyển'),
    (C.STATUS_HIRED, 'Nhận việc'),
]
_STEP_INDEX = {status: i for i, (status, _) in enumerate(PIPELINE_STEPS)}


def _need_action_q(now):
    """Hồ sơ HR cần làm ngay — khớp với cột «Bước tiếp theo»."""
    has_recommend = Exists(CandidateReview.objects.filter(
        candidate=OuterRef('pk'), decision=CandidateReview.DECISION_RECOMMEND,
    ))
    return (
        Q(status=C.STATUS_NEW)
        | (Q(status=C.STATUS_REVIEWING) & Q(has_recommend))
        | Q(status=C.STATUS_INTERVIEWING, interview__result=Interview.RESULT_PASS)
        | Q(status=C.STATUS_INTERVIEWING, interview__result=Interview.RESULT_PENDING, interview__end_time__lte=now)
        | Q(status=C.STATUS_OFFERED)
    )


def _progress(cand):
    """Vị trí trên thanh tiến trình; hồ sơ đã đóng dừng ở bước đã tới."""
    closed = cand.status in (C.STATUS_REJECTED, C.STATUS_NOT_ONBOARDED)
    if cand.status == C.STATUS_NOT_ONBOARDED:
        reached = _STEP_INDEX[C.STATUS_OFFERED]
    elif cand.status == C.STATUS_REJECTED:
        if cand.interview_or_none:
            reached = _STEP_INDEX[C.STATUS_INTERVIEWING]
        elif cand.n_reviews:
            reached = _STEP_INDEX[C.STATUS_REVIEWING]
        else:
            reached = _STEP_INDEX[C.STATUS_NEW]
    else:
        reached = _STEP_INDEX.get(cand.status, 0)
    return [
        {'label': label, 'state': (
            'closed' if closed and i == reached else
            'done' if i < reached or cand.status == C.STATUS_HIRED else
            'current' if i == reached and not closed else 'todo'
        )}
        for i, (_, label) in enumerate(PIPELINE_STEPS)
    ]


def _next_step(cand, now, *, can_move, can_onboard_user):
    """Gợi ý bước tiếp theo + 1 thao tác chính, chỉ khi rule cho phép.

    tone: action (HR cần làm) · wait (chờ người khác) · alert (trễ / vướng) · done · muted
    """
    inv = cand.interview_or_none
    s = cand.status
    if s == C.STATUS_NEW:
        if not cand.job_posting.target_department_id:
            return {'tone': 'alert', 'label': 'Vị trí chưa gắn phòng ban'}
        return {'tone': 'action', 'label': 'Gửi quản lý đánh giá',
                'action': 'move', 'to': C.STATUS_REVIEWING, 'button': 'Gửi đánh giá', 'icon': 'bi-send'}
    if s == C.STATUS_REVIEWING:
        if cand.n_recommend:
            return {'tone': 'action', 'label': 'Lên lịch phỏng vấn',
                    'action': 'move', 'to': C.STATUS_INTERVIEWING, 'button': 'Lên lịch PV', 'icon': 'bi-calendar-plus'}
        if cand.n_reviews:
            return {'tone': 'wait', 'label': 'Chưa có đề xuất phỏng vấn'}
        days = (now - cand.status_changed_at).days if cand.status_changed_at else 0
        return {'tone': 'alert' if days >= 3 else 'wait', 'label': 'Chờ quản lý đánh giá'}
    if s == C.STATUS_INTERVIEWING and inv:
        if inv.result == Interview.RESULT_PASS:
            return {'tone': 'alert', 'label': 'Đạt — vị trí đủ chỉ tiêu'}
        if inv.interview_time > now:
            return {'tone': 'wait', 'label': f'Phỏng vấn {timezone.localtime(inv.interview_time):%H:%M %d/%m}'}
        late = (inv.end_time or inv.interview_time) <= now
        step = {'tone': 'alert' if late else 'wait',
                'label': 'Chờ kết quả phỏng vấn' if late else 'Đang phỏng vấn'}
        if can_move:
            step.update(action='result', button='Nhập kết quả', icon='bi-clipboard-check')
        return step
    if s == C.STATUS_OFFERED:
        step = {'tone': 'action', 'label': 'Onboard nhân viên'}
        if can_onboard_user:
            step.update(action='onboard', button='Onboard', icon='bi-person-badge')
        return step
    if s == C.STATUS_HIRED:
        return {'tone': 'done', 'label': 'Đã nhận việc'}
    return {'tone': 'muted', 'label': cand.get_status_display()}


@module_perm_required(MODULE_RECRUITMENT, 'view')
def candidate_list(request):
    f = _candidate_filters(request)
    now = timezone.now()
    base = _filtered_candidates(request, f, open_jobs_only=True)
    status_counts = dict(base.order_by().values_list('status').annotate(n=Count('id', distinct=True)))
    need_q = _need_action_q(now)
    need_count = Candidate.objects.filter(pk__in=base.values('pk')).filter(need_q).count()
    qs = base
    if f['status'] == NEED_ACTION:
        qs = qs.filter(pk__in=Candidate.objects.filter(need_q).values('pk'))
    elif f['status'] in STATUS_GROUPS:
        qs = qs.filter(status__in=STATUS_GROUPS[f['status']][1])
    elif f['status'] in dict(C.STATUS_CHOICES):
        qs = qs.filter(status=f['status'])
    sort_key = f['sort'] if f['sort'] in CANDIDATE_SORTS else 'moi-nhat'
    qs = qs.order_by(*CANDIDATE_SORTS[sort_key][1])
    page_obj, query_string = paginate_queryset(request, qs)

    ctx = _candidate_page_context(request, 'list', f)
    ctx['jobs'] = ctx['jobs'].filter(status=JobPosting.STATUS_OPEN)
    candidates = list(page_obj.object_list)
    if ctx['can_move']:
        _attach_move_targets(candidates)
    onboard_ok = can_onboard(request.user)
    for cand in candidates:
        cand.progress = _progress(cand)
        cand.next_step = _next_step(cand, now, can_move=ctx['can_move'], can_onboard_user=onboard_ok)

    keep = request.GET.copy()
    keep.pop('page', None)

    def chip_url(key):
        params = keep.copy()
        if key:
            params['status'] = key
        else:
            params.pop('status', None)
        encoded = params.urlencode()
        return f'{request.path}?{encoded}' if encoded else request.path

    chip_specs = [('', 'Tất cả', sum(status_counts.values()), 'all'),
                  (NEED_ACTION, 'Cần xử lý', need_count, 'need')]
    chip_specs += [(key, label, status_counts.get(key, 0), key) for key, label, _ in KANBAN_COLUMNS]
    status_chips = [
        {'key': key, 'label': label, 'count': count, 'tone': tone,
         'active': f['status'] == key, 'url': chip_url(key)}
        for key, label, count, tone in chip_specs
    ]
    if f['status'] in STATUS_GROUPS:
        label, statuses = STATUS_GROUPS[f['status']]
        status_chips.insert(2, {'key': f['status'], 'label': label, 'tone': 'group', 'active': True,
                                'count': sum(status_counts.get(s, 0) for s in statuses), 'url': chip_url(f['status'])})
    return render(request, 'recruitment/admin/candidate_list.html', {
        **ctx,
        'candidates': candidates,
        'page_obj': page_obj,
        'query_string': query_string,
        'status_chips': status_chips,
        'source_choices': CandidateSource.objects.values_list('code', 'name'),
        'sort_options': [(k, v[0]) for k, v in CANDIDATE_SORTS.items()],
        'current_sort': sort_key,
        'can_onboard': onboard_ok,
    })


@module_perm_required(MODULE_RECRUITMENT, 'export')
def export_candidates_excel(request):
    f = _candidate_filters(request)
    qs = _filtered_candidates(request, f, open_jobs_only=True)
    if f['status'] == NEED_ACTION:
        qs = qs.filter(pk__in=Candidate.objects.filter(_need_action_q(timezone.now())).values('pk'))
    elif f['status'] in STATUS_GROUPS:
        qs = qs.filter(status__in=STATUS_GROUPS[f['status']][1])
    elif f['status'] in dict(C.STATUS_CHOICES):
        qs = qs.filter(status=f['status'])
    sort_key = f['sort'] if f['sort'] in CANDIDATE_SORTS else 'moi-nhat'
    qs = qs.order_by(*CANDIDATE_SORTS[sort_key][1])

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Ung vien'
    ws.append(['Họ tên', 'SĐT', 'Email', 'Vị trí', 'Phòng ban', 'Nguồn', 'Trạng thái',
               'Đề xuất PV / đánh giá', 'Lịch PV', 'Kết quả PV', 'Ngày nộp', 'Lý do'])
    for c in qs:
        inv = c.interview_or_none
        ws.append([
            c.full_name, c.phone, c.email, c.job_posting.title, c.job_posting.department_label,
            c.source_label, c.get_status_display(), f'{c.n_recommend}/{c.n_reviews}',
            inv.time_range_label if inv else '',
            inv.get_result_display() if inv else '',
            timezone.localtime(c.applied_at).strftime('%d/%m/%Y'), c.reject_reason,
        ])
    for col, width in zip('ABCDEFGHIJKL', (26, 14, 26, 28, 26, 16, 20, 12, 18, 14, 12, 36)):
        ws.column_dimensions[col].width = width
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="ung_vien_{timezone.localdate():%Y%m%d}.xlsx"'
    wb.save(response)
    return response


@module_perm_required(MODULE_RECRUITMENT, 'view')
def kanban_board(request):
    f = _candidate_filters(request)
    qs = _filtered_candidates(request, f)
    labels = dict((k, (label, css)) for k, label, css in KANBAN_COLUMNS)
    pages, query_string = paginate_columns(
        request,
        [(key, qs.filter(status=key).order_by('-status_changed_at', '-id'), f'p_{key}') for key in KANBAN_BOARD_STATUSES],
        per_page=KANBAN_PAGE_SIZE,
    )
    ctx = _candidate_page_context(request, 'kanban', f)
    columns = []
    for key in KANBAN_BOARD_STATUSES:
        cards = list(pages[key].object_list)
        if ctx['can_move']:
            _attach_move_targets(cards)
        columns.append({
            'key': key, 'label': labels[key][0], 'css': labels[key][1], 'page': pages[key],
            'cards': cards, 'droppable': ctx['can_move'],
            'is_closed': key in (C.STATUS_NOT_ONBOARDED, C.STATUS_REJECTED),
        })
    return render(request, 'recruitment/admin/kanban_board.html', {
        **ctx,
        'columns': columns,
        'query_string': query_string,
        'hired_count': qs.filter(status=C.STATUS_HIRED).count(),
    })


@module_perm_required(MODULE_RECRUITMENT, 'create')
def add_candidate(request):
    jobs = _open_jobs().filter(visible_jobs_q(request.user))
    initial = {}
    if (request.GET.get('job_id') or '').isdigit():
        initial['job_posting'] = int(request.GET['job_id'])
    form = CandidateForm(request.POST or None, request.FILES or None, jobs=jobs, initial=initial)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            cand = services.add_candidate(
                d['job_posting'],
                services.CandidateInput(
                    full_name=d['full_name'], phone=d['phone'], email=d['email'],
                    gender=d['gender'], date_of_birth=d['date_of_birth'],
                    files=d['files'], note=d['note'], source=d['source'],
                ),
                actor=request.user,
                request=request,
            )
        except services.RecruitmentError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã thêm ứng viên {cand.full_name}.')
            return redirect('candidate_detail', pk=cand.pk)
    return render(request, 'recruitment/admin/candidate_form.html', {
        'form': form, 'title': 'Thêm ứng viên', 'back_url': reverse('kanban_board'),
        'has_jobs': jobs.exists(),
    })


@login_required
def candidate_suggest_email(request):
    """Gợi ý email công ty theo họ tên — form thêm / đề xuất ứng viên."""
    if not (can_candidates(request.user, 'create') or is_hiring_manager(request.user)):
        raise PermissionDenied
    return JsonResponse({'email': services.suggest_email(request.GET.get('full_name', ''))})


# ================================================================ Ứng viên — chi tiết & thao tác

def _detail_context(request, candidate, *, manager_view=False, onboard_form=None):
    user = request.user
    interview = candidate.interview_or_none
    reviews = candidate.reviews.select_related('reviewer__profile')
    my_review = next((r for r in reviews if r.reviewer_id == user.pk), None)
    can_update = (not manager_view) and can_candidates(user, 'update')
    review_form = None
    if can_review_candidate(user, candidate):
        review_form = ReviewForm(initial={
            'decision': my_review.decision, 'rating': my_review.rating, 'comment': my_review.comment,
        } if my_review else None)
    targets = []
    if can_update:
        for status in services.allowed_targets(candidate):
            targets.append((status, services.status_label(status)))
    show_onboard = (not manager_view) and candidate.status == C.STATUS_OFFERED and can_onboard(user)
    can_manage_files = can_update or (
        manager_view and candidate.referred_by_id == user.pk and candidate.status == C.STATUS_NEW
    )
    return {
        'candidate': candidate,
        'files': list(candidate.files.all()),
        'file_form': CandidateFileForm() if can_manage_files else None,
        'can_delete_files': can_update,
        'interview': interview,
        'reviews': reviews,
        'review_form': review_form,
        'my_review': my_review,
        'manager_view': manager_view,
        'can_update': can_update,
        'targets': targets,
        'transition_form': TransitionForm(),
        'interview_locations': _interview_locations() if can_update else [],
        'needs_review_for_interview': (
            candidate.status == C.STATUS_REVIEWING and not services.has_recommend_review(candidate)
        ),
        'result_form': InterviewResultForm() if can_record_interview_result(user, candidate) else None,
        'result_action': reverse(
            'recruitment_review_interview_result' if manager_view else 'candidate_interview_result',
            args=[candidate.pk],
        ),
        'interview_started': bool(interview and interview.interview_time <= timezone.now()),
        'can_onboard': show_onboard,
        'onboard_form': (onboard_form or OnboardForm(
            candidate=candidate,
            suggested_email='' if candidate.email else services.suggest_email(candidate.full_name),
        )) if show_onboard else None,
        'onboarding_course': services.onboarding_course() if candidate.status == C.STATUS_OFFERED else None,
        'onboarding_group': services.onboarding_permission_group() if candidate.status == C.STATUS_OFFERED else None,
        'filled': services.filled_count(candidate.job_posting),
    }


@module_perm_required(MODULE_RECRUITMENT, 'view')
def candidate_detail(request, pk):
    candidate = _get_candidate(request, pk)
    return render(request, 'recruitment/admin/candidate_detail.html', _detail_context(request, candidate))


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def candidate_transition(request, pk):
    candidate = _get_candidate(request, pk)
    form = TransitionForm(request.POST)
    back = request.POST.get('next') or reverse('candidate_detail', args=[pk])
    if not back.startswith('/'):
        back = reverse('candidate_detail', args=[pk])
    if not form.is_valid():
        messages.error(request, 'Dữ liệu chuyển trạng thái không hợp lệ.')
        return redirect(back)
    d = form.cleaned_data
    try:
        services.transition(
            candidate, d['to_status'], actor=request.user, reason=d['reason'],
            interview_time=d['interview_time'], interview_end=d['interview_end'],
            location=d['location'], interviewers=d['interviewers'],
        )
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'{candidate.full_name}: {services.status_label(d["to_status"])}.')
    return redirect(back)


def _save_interview_result(request, candidate):
    form = InterviewResultForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Chọn kết quả phỏng vấn.')
        return False
    try:
        outcome = services.record_interview_result(
            candidate, form.cleaned_data['result'], form.cleaned_data['notes'], actor=request.user,
        )
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
        return False
    (messages.success if outcome.auto_status else messages.warning)(request, outcome.message)
    return True


def _safe_next(request, fallback):
    nxt = request.POST.get('next') or ''
    return nxt if nxt.startswith('/') and not nxt.startswith('//') else fallback


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def candidate_interview_result(request, pk):
    candidate = _get_candidate(request, pk)
    _save_interview_result(request, candidate)
    return redirect(_safe_next(request, reverse('candidate_detail', args=[pk])))


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def candidate_onboard(request, pk):
    candidate = _get_candidate(request, pk)
    if not can_onboard(request.user):
        messages.error(request, 'Onboard cần thêm quyền «Thêm» ở Danh sách nhân viên (Nhân sự).')
        return redirect('candidate_detail', pk=pk)
    form = OnboardForm(request.POST, candidate=candidate)
    if not form.is_valid():
        messages.error(request, 'Kiểm tra lại thông tin onboard.')
        return render(request, 'recruitment/admin/candidate_detail.html',
                      _detail_context(request, candidate, onboard_form=form))
    d = form.cleaned_data
    try:
        result = services.onboard_candidate(
            candidate, actor=request.user, join_date=d['join_date'],
            email=d['email'], gender=d['gender'], date_of_birth=d['date_of_birth'],
        )
    except services.RecruitmentError as exc:
        return _fail(request, exc, reverse('candidate_detail', args=[pk]))
    if not result.course_title:
        messages.warning(request, f'Chưa có khóa «{services.ONBOARDING_COURSE_TITLE}» đang hoạt động để giao.')
    # Hiển thị mật khẩu một lần trên trang kết quả (không lưu, không gửi qua flash 3 giây).
    response = render(request, 'recruitment/admin/onboard_result.html', {
        'candidate': candidate, 'result': result,
    })
    response['Cache-Control'] = 'no-store'
    return response


# ================================================================ Hồ sơ đính kèm (CV)

@login_required
def candidate_file(request, pk):
    """Trả file hồ sơ — kiểm tra quyền mỗi lần, không có link /media/ công khai."""
    obj = get_object_or_404(CandidateFile.objects.select_related('candidate__job_posting'), pk=pk)
    if not can_view_candidate(request.user, obj.candidate):
        raise PermissionDenied
    try:
        handle = obj.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('File không còn trên máy chủ.')
    download = request.GET.get('download') == '1' or obj.preview_kind == 'download'
    response = FileResponse(handle, content_type=obj.content_type, as_attachment=download,
                            filename=obj.original_name)
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def candidate_file_upload(request, pk):
    candidate = _get_candidate(request, pk)
    return _upload_files(request, candidate, reverse('candidate_detail', args=[pk]))


@_manager_required
@require_POST
def manager_file_upload(request, pk):
    """Quản lý bổ sung hồ sơ cho ứng viên mình đề xuất (khi HR chưa tiếp nhận)."""
    candidate = get_object_or_404(Candidate, pk=pk, referred_by=request.user, status=C.STATUS_NEW)
    return _upload_files(request, candidate, reverse('recruitment_review_candidate', args=[pk]))


def _upload_files(request, candidate, back):
    form = CandidateFileForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, ' '.join(e for errs in form.errors.values() for e in errs))
        return redirect(back)
    try:
        created = services.attach_files(
            candidate, form.cleaned_data['files'], actor=request.user,
            kind=form.cleaned_data['kind'], request=request,
        )
        messages.success(request, f'Đã lưu {len(created)} file hồ sơ.')
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    return redirect(back)


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def candidate_file_delete(request, pk, file_pk):
    obj = get_object_or_404(CandidateFile, pk=file_pk, candidate__in=_cands(request).filter(pk=pk))
    services.remove_file(obj, actor=request.user)
    messages.success(request, f'Đã xóa file {obj.original_name}.')
    return redirect('candidate_detail', pk=pk)


# ================================================================ Lịch phỏng vấn

def _interview_range(request):
    today = timezone.localdate()
    span = parse_date_range_span_from_request(request)
    raw_from, raw_to = request.GET.get('from'), request.GET.get('to')
    try:
        d_from = datetime.strptime(raw_from, '%Y-%m-%d').date() if raw_from else None
        d_to = datetime.strptime(raw_to, '%Y-%m-%d').date() if raw_to else None
    except ValueError:
        d_from = d_to = None
    if not d_from and not d_to:
        # Mặc định: các buổi phỏng vấn sắp tới trong khoảng preset.
        d_from, d_to = today, today + timedelta(days=span - 1)
    d_from = d_from or (d_to - timedelta(days=span - 1))
    d_to = d_to or (d_from + timedelta(days=span - 1))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    return d_from, d_to


def _interview_queryset(request):
    d_from, d_to = _interview_range(request)
    qs = _interviews(request).select_related(
        'candidate', 'candidate__job_posting', 'candidate__job_posting__target_department',
    ).prefetch_related('interviewers__profile', 'candidate__files').filter(
        interview_time__date__gte=d_from, interview_time__date__lte=d_to,
    )
    job_id = (request.GET.get('job_id') or '').strip()
    if job_id.isdigit():
        qs = qs.filter(candidate__job_posting_id=int(job_id))
    result = (request.GET.get('result') or '').strip()
    if result in dict(Interview.RESULT_CHOICES):
        qs = qs.filter(result=result)
    return qs.order_by('interview_time'), d_from, d_to


@module_perm_required(MODULE_RECRUITMENT, 'view')
def interview_list(request):
    qs, d_from, d_to = _interview_queryset(request)
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'recruitment/admin/interview_list.html', {
        'interviews': page_obj.object_list,
        'page_obj': page_obj,
        'query_string': query_string,
        'date_from': d_from,
        'date_to': d_to,
        'jobs': _jobs(request).exclude(status=JobPosting.STATUS_DRAFT).order_by('title'),
        'selected_job': request.GET.get('job_id', ''),
        'result_filter': request.GET.get('result', ''),
        'result_choices': Interview.RESULT_CHOICES,
        'can_export': can_candidates(request.user, 'export'),
        'now': timezone.now(),
        **date_range_span_context(d_from, d_to),
    })


@module_perm_required(MODULE_RECRUITMENT, 'export')
def export_interviews_excel(request):
    qs, d_from, d_to = _interview_queryset(request)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = 'Lich phong van'
    ws.append(['Bắt đầu', 'Kết thúc', 'Thời lượng (phút)', 'Ứng viên', 'SĐT', 'Vị trí', 'Phòng ban', 'Địa điểm',
               'Người phỏng vấn', 'Kết quả', 'Nhận xét'])
    for inv in qs:
        cand = inv.candidate
        ws.append([
            timezone.localtime(inv.interview_time).strftime('%H:%M %d/%m/%Y'),
            timezone.localtime(inv.end_time).strftime('%H:%M %d/%m/%Y') if inv.end_time else '',
            inv.duration_minutes,
            cand.full_name,
            cand.phone,
            cand.job_posting.title,
            cand.job_posting.department_label,
            inv.location,
            ', '.join(
                (getattr(getattr(u, 'profile', None), 'full_name', '') or u.username)
                for u in inv.interviewers.all()
            ),
            inv.get_result_display(),
            inv.result_notes,
        ])
    for col, width in zip('ABCDEFGHIJK', (18, 18, 12, 26, 14, 28, 22, 22, 30, 16, 40)):
        ws.column_dimensions[col].width = width
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = (
        f'attachment; filename="lich_phong_van_{d_from:%Y%m%d}_{d_to:%Y%m%d}.xlsx"'
    )
    wb.save(response)
    return response


# ================================================================ Quản lý: đề xuất & đánh giá

@_reviewer_required
def review_list(request):
    user = request.user
    is_manager = is_hiring_manager(user)
    interviews = (
        _candidate_qs().filter(pk__in=interview_queue(user).values('pk'))
        .select_related('interview').order_by('interview__interview_time')
    )
    tabs_spec = []
    if is_manager:
        base = _managed_candidates(user)
        my_reviews = CandidateReview.objects.filter(reviewer=user)
        pending = _pending_reviews(user)
        reviewed = (
            base.filter(pk__in=my_reviews.values('candidate_id'))
            .annotate(my_review_at=Max('reviews__updated_at', filter=Q(reviews__reviewer=user)))
            .prefetch_related(Prefetch('reviews', queryset=my_reviews, to_attr='my_reviews'))
            .order_by('-my_review_at')
        )
        referred = (
            Candidate.objects.select_related('job_posting', 'job_posting__target_department')
            .prefetch_related('files')
            .filter(referred_by=user).order_by('-applied_at')
        )
        tabs_spec = [
            ('cho-danh-gia', 'Chờ đánh giá', pending),
            ('phong-van', 'Kết quả phỏng vấn', interviews),
            ('da-danh-gia', 'Đã đánh giá', reviewed),
            ('da-de-xuat', 'Tôi đề xuất', referred),
        ]
    else:
        tabs_spec = [('phong-van', 'Kết quả phỏng vấn', interviews)]
    current = request.GET.get('tab') or tabs_spec[0][0]
    if current not in {key for key, _, _ in tabs_spec}:
        current = tabs_spec[0][0]
    tabs = [
        {'key': key, 'label': label, 'count': qs.count(), 'active': key == current,
         'url': f'{reverse("recruitment_review_list")}?tab={key}'}
        for key, label, qs in tabs_spec
    ]
    active_qs = next(qs for key, _, qs in tabs_spec if key == current)
    page_obj, query_string = paginate_queryset(request, active_qs)
    return render(request, 'recruitment/manager/review_list.html', {
        'tabs': tabs,
        'current_tab': current,
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'now': timezone.now(),
        'result_form': InterviewResultForm(),
        'open_jobs_in_scope': is_manager and _open_jobs().filter(manager_job_filter(user)).exists(),
        'scope_label': (
            scope_label(user, managed=True) if is_manager else 'Các buổi phỏng vấn bạn được giao'
        ),
    })


def _reviewer_candidate(request, pk):
    candidate = get_object_or_404(_candidate_qs(), pk=pk)
    user = request.user
    if not (
        (is_hiring_manager(user) and manager_can_access_job(user, candidate.job_posting))
        or is_interviewer(user, candidate)
    ):
        raise PermissionDenied
    return candidate


@login_required
@require_POST
def review_interview_result(request, pk):
    candidate = _reviewer_candidate(request, pk)
    _save_interview_result(request, candidate)
    return redirect(_safe_next(request, f'{reverse("recruitment_review_list")}?tab=phong-van'))


def _managed_candidates(user):
    return _candidate_qs().filter(job_posting__in=JobPosting.objects.filter(manager_job_filter(user)))


def _pending_reviews(user):
    """Hồ sơ đang chờ đánh giá mà quản lý này chưa đánh giá — cũ nhất trước."""
    return (
        _managed_candidates(user).filter(status=C.STATUS_REVIEWING)
        .exclude(reviews__reviewer=user)
        .order_by('status_changed_at', 'pk')
    )


@login_required
def review_candidate(request, pk):
    candidate = _reviewer_candidate(request, pk)
    user = request.user
    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            try:
                services.submit_review(
                    candidate, user,
                    decision=form.cleaned_data['decision'],
                    rating=form.cleaned_data['rating'],
                    comment=form.cleaned_data['comment'],
                )
            except services.RecruitmentError as exc:
                messages.error(request, str(exc))
            else:
                nxt = _pending_reviews(user).exclude(pk=candidate.pk).first() if is_hiring_manager(user) else None
                if nxt:
                    messages.success(request, f'Đã gửi đánh giá cho {candidate.full_name}. Tiếp theo: {nxt.full_name}.')
                    return redirect('recruitment_review_candidate', pk=nxt.pk)
                messages.success(request, f'Đã gửi đánh giá cho {candidate.full_name}.')
                return redirect('recruitment_review_list')
        else:
            messages.error(request, 'Chọn kết luận đánh giá.')
        return redirect('recruitment_review_candidate', pk=pk)
    ctx = _detail_context(request, candidate, manager_view=True)
    reviews = list(ctx['reviews'])
    files = ctx['files']
    primary = candidate.primary_file
    pending_ids = list(_pending_reviews(user).values_list('pk', flat=True)) if is_hiring_manager(user) else []
    ctx.update({
        'reviews': reviews,
        'other_reviews': [r for r in reviews if r.reviewer_id != user.pk],
        'viewer_file': primary or (files[0] if files else None),
        'decision_choices': [
            (value, label, REVIEW_DECISION_UI[value]) for value, label in CandidateReview.DECISION_CHOICES
            if value in CandidateReview.ACTIVE_DECISIONS
        ],
        'pending_left': len([i for i in pending_ids if i != candidate.pk]),
        'skip_candidate': next((i for i in pending_ids if i != candidate.pk), None),
    })
    return render(request, 'recruitment/manager/review_candidate.html', ctx)


@_manager_required
def refer_candidate(request):
    jobs = _open_jobs().filter(manager_job_filter(request.user))
    form = CandidateForm(request.POST or None, request.FILES or None, jobs=jobs, referral=True)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            cand = services.add_candidate(
                d['job_posting'],
                services.CandidateInput(
                    full_name=d['full_name'], phone=d['phone'], email=d['email'],
                    gender=d['gender'], date_of_birth=d['date_of_birth'],
                    files=d['files'], note=d['note'], source=C.SOURCE_REFERRAL,
                ),
                actor=request.user,
                referred_by=request.user,
                request=request,
            )
        except services.RecruitmentError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã đề xuất ứng viên {cand.full_name} — HR sẽ tiếp nhận hồ sơ.')
            return redirect('recruitment_review_list')
    return render(request, 'recruitment/admin/candidate_form.html', {
        'form': form, 'title': 'Đề xuất ứng viên', 'back_url': reverse('recruitment_review_list'),
        'has_jobs': jobs.exists(), 'referral': True,
    })


# ================================================================ Thiết lập (menu «settings»)

SETTINGS_TABS = {
    'dia-diem': {
        'model': InterviewLocation, 'form': InterviewLocationForm, 'label': 'Địa điểm họp', 'icon': 'bi-geo-alt',
        'singular': 'địa điểm', 'hint': 'Chọn nhanh khi lên lịch phỏng vấn. Đổi tên sẽ cập nhật các lịch chưa có kết quả.',
    },
    'loai-ho-so': {
        'model': CandidateFileKind, 'form': CandidateFileKindForm, 'label': 'Loại hồ sơ',
        'icon': 'bi-file-earmark-text', 'singular': 'loại hồ sơ',
        'hint': 'Phân loại file đính kèm. Loại «Là CV» được mở khi bấm «Xem CV».',
    },
    'nguon-ho-so': {
        'model': CandidateSource, 'form': CandidateSourceForm, 'label': 'Nguồn hồ sơ', 'icon': 'bi-signpost-split',
        'singular': 'nguồn', 'hint': 'Lựa chọn bắt buộc khi thêm ứng viên. «Quản lý đề xuất» do hệ thống tự gán.',
    },
}


def _settings_usage(tab):
    if tab == 'nguon-ho-so':
        rows = Candidate.objects.values_list('source').annotate(n=Count('id'))
    elif tab == 'loai-ho-so':
        rows = CandidateFile.objects.values_list('kind').annotate(n=Count('id'))
    else:
        rows = Interview.objects.exclude(location='').values_list('location').annotate(n=Count('id'))
    return dict(rows)


def _settings_url(tab):
    return f'{reverse("recruitment_settings")}?tab={tab}'


@module_perm_required(MODULE_RECRUITMENT, 'view')
def recruitment_settings(request, create_form=None, create_tab=None):
    tab = create_tab or request.GET.get('tab')
    if tab not in SETTINGS_TABS:
        tab = next(iter(SETTINGS_TABS))
    spec = SETTINGS_TABS[tab]
    usage = _settings_usage(tab)
    items = list(spec['model'].objects.all())
    for item in items:
        item.usage = usage.get(getattr(item, 'code', None) or item.name, 0)
    user = request.user
    return render(request, 'recruitment/admin/settings.html', {
        'tabs': [
            {'key': key, 'label': s['label'], 'icon': s['icon'], 'active': key == tab, 'url': _settings_url(key),
             'count': s['model'].objects.filter(is_active=True).count()}
            for key, s in SETTINGS_TABS.items()
        ],
        'tab': tab,
        'spec': spec,
        'items': items,
        'create_form': create_form or spec['form'](),
        'can_create': can_settings(user, 'create'),
        'can_update': can_settings(user, 'update'),
        'can_delete': can_settings(user, 'delete'),
    })


def _settings_item(tab, pk):
    if tab not in SETTINGS_TABS:
        raise Http404
    return get_object_or_404(SETTINGS_TABS[tab]['model'], pk=pk)


@module_perm_required(MODULE_RECRUITMENT, 'create')
@require_POST
def recruitment_settings_add(request, tab):
    if tab not in SETTINGS_TABS:
        raise Http404
    spec = SETTINGS_TABS[tab]
    form = spec['form'](request.POST)
    if not form.is_valid():
        return recruitment_settings(request, create_form=form, create_tab=tab)
    try:
        obj = services.save_option(form)
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Đã thêm {spec["singular"]} «{obj.name}».')
    return redirect(_settings_url(tab))


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def recruitment_settings_edit(request, tab, pk):
    obj = _settings_item(tab, pk)
    form = SETTINGS_TABS[tab]['form'](request.POST, instance=obj)
    if not form.is_valid():
        messages.error(request, ' '.join(e for errs in form.errors.values() for e in errs))
        return redirect(_settings_url(tab))
    try:
        obj = services.save_option(form)
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Đã cập nhật «{obj.name}».')
    return redirect(_settings_url(tab))


@module_perm_required(MODULE_RECRUITMENT, 'update')
@require_POST
def recruitment_settings_toggle(request, tab, pk):
    obj = _settings_item(tab, pk)
    try:
        services.toggle_option(obj)
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'«{obj.name}»: {"đang dùng" if obj.is_active else "ngừng dùng"}.')
    return redirect(_settings_url(tab))


@module_perm_required(MODULE_RECRUITMENT, 'delete')
@require_POST
def recruitment_settings_delete(request, tab, pk):
    obj = _settings_item(tab, pk)
    try:
        name = services.delete_option(obj)
    except services.RecruitmentError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f'Đã xóa «{name}».')
    return redirect(_settings_url(tab))
