from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from django.db.models import Q

from hrm.module_permissions import MODULE_SERVICE_REQUESTS, user_can_access_module
from PortalJustPlay.list_search import apply_combined_search, apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from tasks.attachment_utils import read_separate_uploads

from .forms import RejectStepForm, ServiceRequestCreateForm, StepActionForm
from .models import ServiceRequest, ServiceRequestAttachment, ServiceRequestStep
from .permissions import can_claim_step, can_handle_step, can_view_request, pending_steps_for_user
from .workflow import (
    approve_step,
    cancel_request,
    claim_step,
    complete_execution_step,
    create_request_with_steps,
    get_active_request_type,
    log_action,
    reject_step,
)


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_SERVICE_REQUESTS):
            messages.error(request, 'Bạn không có quyền truy cập module Yêu cầu.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _save_attachments(request_obj, prepared_files, *, uploaded_by, stage, step=None):
    for original_name, content_file in prepared_files:
        ServiceRequestAttachment.objects.create(
            request=request_obj,
            step=step,
            file=content_file,
            original_name=original_name,
            uploaded_by=uploaded_by,
            stage=stage,
        )


@_access_required
def request_hub(request):
    return redirect('service_requests:my')


@_access_required
def my_requests(request):
    search_query = get_search_query(request)
    qs = ServiceRequest.objects.filter(
        requester=request.user,
    ).select_related('request_type').prefetch_related('steps')
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    qs = apply_term_search(
        qs, search_query,
        'title__icontains', 'description__icontains', 'request_type__name__icontains',
    )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'service_requests/my_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'current_status': status,
        'status_tabs': [
            ('', 'Tất cả'),
            (ServiceRequest.STATUS_IN_PROGRESS, 'Đang xử lý'),
            (ServiceRequest.STATUS_COMPLETED, 'Hoàn thành'),
            (ServiceRequest.STATUS_REJECTED, 'Từ chối'),
            (ServiceRequest.STATUS_CANCELLED, 'Đã hủy'),
        ],
        'pending_count': pending_steps_for_user(request.user).count(),
    })


@_access_required
def pending_requests(request):
    search_query = get_search_query(request)
    qs = pending_steps_for_user(request.user)
    qs = apply_combined_search(qs, search_query, lambda term: (
        Q(request__title__icontains=term)
        | Q(request__description__icontains=term)
        | Q(name__icontains=term)
        | Q(request__requester__username__icontains=term)
        | Q(request__requester__profile__full_name__icontains=term)
        | Q(request__requester__profile__employee_code__icontains=term)
    ))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'service_requests/pending_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'pending_count': qs.count(),
    })


@_access_required
def create_request(request):
    request_type = get_active_request_type()
    if not request_type:
        messages.warning(
            request,
            'Chưa cấu hình loại yêu cầu. Liên hệ quản trị viên.',
        )
        return redirect('service_requests:my')

    if request.method == 'POST':
        form = ServiceRequestCreateForm(request.POST, request_type=request_type)
        if form.is_valid():
            try:
                service_request = create_request_with_steps(
                    requester=request.user,
                    request_type=request_type,
                    title=form.cleaned_data['title'],
                    description=form.cleaned_data['description'],
                    estimated_cost=form.cleaned_data.get('estimated_cost'),
                )
                prepared = read_separate_uploads(
                    request.FILES.getlist('images'),
                    request.FILES.getlist('files'),
                )
                if prepared:
                    _save_attachments(
                        service_request,
                        prepared,
                        uploaded_by=request.user,
                        stage=ServiceRequestAttachment.STAGE_REQUEST,
                    )
                    log_action(
                        service_request,
                        actor=request.user,
                        action='attachment',
                        message=f'Đính kèm {len(prepared)} file',
                    )
                messages.success(request, 'Đã gửi yêu cầu — đang chờ xử lý theo quy trình.')
                return redirect('service_requests:detail', pk=service_request.pk)
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        form = ServiceRequestCreateForm(request_type=request_type)

    return render(request, 'service_requests/form.html', {
        'form': form,
        'request_type': request_type,
        'pending_count': pending_steps_for_user(request.user).count(),
    })


@_access_required
def request_detail(request, pk):
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related(
            'requester', 'requester__profile', 'request_type',
        ).prefetch_related(
            'steps__assignee__profile',
            'steps__target_department',
            'attachments__uploaded_by',
            'logs__actor__profile',
            'logs__step',
        ),
        pk=pk,
    )
    if not can_view_request(request.user, service_request):
        messages.error(request, 'Bạn không có quyền xem yêu cầu này.')
        return redirect('service_requests:my')

    current_step = service_request.current_step
    can_handle_current = bool(current_step and can_handle_step(request.user, current_step))
    can_claim_current = bool(current_step and can_claim_step(request.user, current_step))

    action_form = StepActionForm()
    reject_form = RejectStepForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'cancel' and service_request.requester_id == request.user.id:
                cancel_request(service_request, actor=request.user)
                messages.info(request, 'Đã hủy yêu cầu.')
                return redirect('service_requests:my')

            if not current_step:
                messages.error(request, 'Yêu cầu không còn bước đang xử lý.')
                return redirect('service_requests:detail', pk=pk)

            if action == 'claim' and can_claim_current:
                claim_step(current_step, actor=request.user)
                messages.success(request, 'Đã tiếp nhận yêu cầu.')
                return redirect('service_requests:detail', pk=pk)

            if action == 'approve' and can_handle_current and current_step.is_approval:
                action_form = StepActionForm(request.POST)
                if action_form.is_valid():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    approve_step(current_step, actor=request.user, note=action_form.cleaned_data.get('note', ''))
                    messages.success(request, 'Đã duyệt bước này.')
                    return redirect('service_requests:detail', pk=pk)

            if action == 'reject' and can_handle_current and current_step.is_approval:
                reject_form = RejectStepForm(request.POST)
                if reject_form.is_valid():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    reject_step(current_step, actor=request.user, reason=reject_form.cleaned_data['reason'])
                    messages.info(request, 'Đã từ chối yêu cầu.')
                    return redirect('service_requests:detail', pk=pk)

            if action == 'complete' and can_handle_current and current_step.is_execution:
                action_form = StepActionForm(request.POST)
                if action_form.is_valid() and action_form.cleaned_data.get('note', '').strip():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    prepared = read_separate_uploads(
                        request.FILES.getlist('images'),
                        request.FILES.getlist('files'),
                    )
                    complete_execution_step(
                        current_step,
                        actor=request.user,
                        note=action_form.cleaned_data['note'].strip(),
                    )
                    if prepared:
                        _save_attachments(
                            service_request,
                            prepared,
                            uploaded_by=request.user,
                            stage=ServiceRequestAttachment.STAGE_RESULT,
                            step=current_step,
                        )
                    messages.success(request, 'Đã hoàn thành bước thực hiện.')
                    return redirect('service_requests:detail', pk=pk)
                messages.error(request, 'Vui lòng nhập kết quả xử lý.')

        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect('service_requests:detail', pk=pk)

    can_cancel = (
        service_request.requester_id == request.user.id
        and service_request.status == ServiceRequest.STATUS_IN_PROGRESS
        and service_request.steps.order_by('step_order').first().status == ServiceRequestStep.STATUS_PENDING
    )

    return render(request, 'service_requests/detail.html', {
        'service_request': service_request,
        'steps': service_request.steps.all(),
        'logs': service_request.logs.all(),
        'request_attachments': service_request.attachments.filter(stage=ServiceRequestAttachment.STAGE_REQUEST),
        'current_step': current_step,
        'can_handle_current': can_handle_current,
        'can_claim_current': can_claim_current,
        'can_cancel': can_cancel,
        'action_form': action_form,
        'reject_form': reject_form,
        'pending_count': pending_steps_for_user(request.user).count(),
    })
