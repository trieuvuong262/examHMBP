import uuid

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from hrm.module_permissions import MODULE_TASKS, user_can_access_module
from hrm.permissions import (
    can_assign_tasks,
    can_manage_assigned_task,
    can_view_task,
    get_report_team_users,
)
from PortalJustPlay.pagination import paginate_queryset

from .forms import (
    WorkTaskAssignForm,
    WorkTaskProgressForm,
    WorkTaskRejectForm,
    WorkTaskReassignForm,
    WorkTaskReviewForm,
    WorkTaskSubmitForm,
)
from .models import WorkTask, WorkTaskAttachment, WorkTaskHandoff, WorkTaskLog
from .attachment_utils import read_separate_uploads, save_task_attachments, copy_task_attachments
from .project_utils import unlock_dependent_steps
from .utils import log_task_action


def _tasks_access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_TASKS):
            messages.error(request, 'Bạn không có quyền truy cập module Công việc.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _assign_access_required(view_func):
    @_tasks_access_required
    def wrapper(request, *args, **kwargs):
        if not can_assign_tasks(request.user):
            messages.error(request, 'Bạn chưa có quyền giao việc. Cần quyền cập nhật module và nhân viên cấp dưới trực tiếp.')
            return redirect('tasks:my')
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_task_or_404(user, pk):
    task = get_object_or_404(
        WorkTask.objects.select_related('assigner', 'assignee', 'assignee__profile', 'assigner__profile'),
        pk=pk,
    )
    if not can_view_task(user, task):
        return None
    return task


STATUS_TABS = [
    ('', 'Tất cả'),
    (WorkTask.STATUS_PENDING_ACK, 'Chờ xác nhận'),
    (WorkTask.STATUS_IN_PROGRESS, 'Đang làm'),
    (WorkTask.STATUS_PENDING_REVIEW, 'Chờ duyệt'),
    (WorkTask.STATUS_REVISION, 'Cần sửa'),
    (WorkTask.STATUS_COMPLETED, 'Hoàn thành'),
    (WorkTask.STATUS_REJECTED, 'Từ chối'),
]


@_tasks_access_required
def task_hub(request):
    if can_assign_tasks(request.user):
        pending_assigned = WorkTask.objects.filter(
            assigner=request.user,
            status__in={WorkTask.STATUS_PENDING_REVIEW, WorkTask.STATUS_REJECTED},
        ).count()
        if pending_assigned:
            return redirect('tasks:assigned')
    return redirect('tasks:my')


@_tasks_access_required
def my_tasks(request):
    status = request.GET.get('status', '')
    qs = WorkTask.objects.filter(assignee=request.user).select_related(
        'assigner', 'assigner__profile',
    )
    if status:
        qs = qs.filter(status=status)
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'tasks/my_tasks.html', {
        'page_obj': page_obj,
        'status_tabs': STATUS_TABS,
        'current_status': status,
        'query_string': query_string,
        'can_assign': can_assign_tasks(request.user),
        'pending_ack_count': WorkTask.objects.filter(
            assignee=request.user, status=WorkTask.STATUS_PENDING_ACK,
        ).count(),
    })


@_tasks_access_required
def assigned_tasks(request):
    if not can_assign_tasks(request.user):
        messages.info(request, 'Danh sách việc đã giao dành cho người có quyền giao việc.')
        return redirect('tasks:my')

    status = request.GET.get('status', '')
    qs = WorkTask.objects.filter(assigner=request.user).select_related(
        'assignee', 'assignee__profile',
    )
    if status:
        qs = qs.filter(status=status)
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'tasks/assigned.html', {
        'page_obj': page_obj,
        'status_tabs': STATUS_TABS,
        'current_status': status,
        'query_string': query_string,
        'can_assign': True,
        'pending_review_count': WorkTask.objects.filter(
            assigner=request.user, status=WorkTask.STATUS_PENDING_REVIEW,
        ).count(),
        'rejected_count': WorkTask.objects.filter(
            assigner=request.user, status=WorkTask.STATUS_REJECTED,
        ).count(),
    })


ASSIGNEE_UPLOAD_STATUSES = {
    WorkTask.STATUS_IN_PROGRESS,
    WorkTask.STATUS_REVISION,
    WorkTask.STATUS_PENDING_REVIEW,
}


def _task_attachments(task):
    return task.attachments.select_related('uploaded_by', 'uploaded_by__profile')


def _split_attachments(queryset):
    images, files = [], []
    for att in queryset:
        (images if att.is_image else files).append(att)
    return images, files


def _read_request_uploads(request):
    return read_separate_uploads(
        request.FILES.getlist('images'),
        request.FILES.getlist('files'),
    )


def _handle_attachment_upload(request, task, *, stage, actor):
    if not request.FILES.getlist('images') and not request.FILES.getlist('files'):
        messages.warning(request, 'Chưa chọn hình ảnh hoặc file nào để tải lên.')
        return False
    try:
        prepared = _read_request_uploads(request)
    except ValidationError as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return False
    saved = save_task_attachments(task, prepared, uploaded_by=actor, stage=stage)
    image_count = sum(1 for att in saved if att.is_image)
    file_count = len(saved) - image_count
    parts = []
    if image_count:
        parts.append(f'{image_count} hình ảnh')
    if file_count:
        parts.append(f'{file_count} file')
    log_task_action(
        task,
        actor,
        WorkTaskLog.ACTION_ATTACHMENT,
        f'Tải lên {", ".join(parts) or len(saved)}',
    )
    messages.success(request, f'Đã tải lên {", ".join(parts)}.')
    return True


@_assign_access_required
def assign_task(request):
    if request.method == 'POST':
        form = WorkTaskAssignForm(request.POST, assigner=request.user)
        if form.is_valid():
            assignees = form.cleaned_data['assignees']
            batch = uuid.uuid4()
            prepared_files = []
            try:
                prepared_files = _read_request_uploads(request)
            except ValidationError as exc:
                messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
                return render(request, 'tasks/assign.html', {
                    'form': form,
                    'team_count': get_report_team_users(request.user).count(),
                })

            created = []
            for assignee in assignees:
                task = WorkTask.objects.create(
                    assignment_batch=batch,
                    title=form.cleaned_data['title'],
                    description=form.cleaned_data['description'],
                    task_type=form.cleaned_data['task_type'],
                    priority=form.cleaned_data['priority'],
                    due_date=form.cleaned_data['due_date'],
                    assigner=request.user,
                    assignee=assignee,
                )
                if prepared_files:
                    save_task_attachments(
                        task,
                        prepared_files,
                        uploaded_by=request.user,
                        stage=WorkTaskAttachment.STAGE_ASSIGN,
                    )
                log_task_action(task, request.user, WorkTaskLog.ACTION_ASSIGNED, f'Giao cho {assignee.username}')
                created.append(task)
            count = len(created)
            messages.success(request, f'Đã giao {count} công việc — mỗi người một bản ghi riêng.')
            if count == 1:
                return redirect('tasks:detail', pk=created[0].pk)
            return redirect('tasks:assigned')
    else:
        form = WorkTaskAssignForm(assigner=request.user)

    return render(request, 'tasks/assign.html', {
        'form': form,
        'team_count': get_report_team_users(request.user).count(),
    })


@_tasks_access_required
def task_detail(request, pk):
    task = _get_task_or_404(request.user, pk)
    if task is None:
        messages.error(request, 'Không tìm thấy công việc hoặc bạn không có quyền xem.')
        return redirect('tasks:my')

    is_assignee = task.assignee_id == request.user.id
    is_assigner = can_manage_assigned_task(request.user, task)

    progress_form = WorkTaskProgressForm(
        initial={'progress_percent': task.progress_percent, 'result_note': task.result_note},
    )
    submit_form = WorkTaskSubmitForm(initial={'result_note': task.result_note})
    reject_form = WorkTaskRejectForm()
    review_form = WorkTaskReviewForm(initial={'review_note': task.review_note})

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'upload_attachment' and is_assignee and task.status in ASSIGNEE_UPLOAD_STATUSES:
            if _handle_attachment_upload(
                request,
                task,
                stage=WorkTaskAttachment.STAGE_WORK,
                actor=request.user,
            ):
                return redirect('tasks:detail', pk=pk)

        if action == 'acknowledge' and is_assignee and task.status == WorkTask.STATUS_PENDING_ACK:
            task.status = WorkTask.STATUS_IN_PROGRESS
            task.acknowledged_at = timezone.now()
            task.save(update_fields=['status', 'acknowledged_at', 'updated_at'])
            log_task_action(task, request.user, WorkTaskLog.ACTION_ACK, 'Đã xác nhận nhận việc')
            messages.success(request, 'Đã xác nhận công việc.')
            return redirect('tasks:detail', pk=pk)

        if action == 'reject' and is_assignee and task.status == WorkTask.STATUS_PENDING_ACK:
            reject_form = WorkTaskRejectForm(request.POST)
            if reject_form.is_valid():
                task.status = WorkTask.STATUS_REJECTED
                task.reject_reason = reject_form.cleaned_data['reject_reason']
                task.save(update_fields=['status', 'reject_reason', 'updated_at'])
                log_task_action(task, request.user, WorkTaskLog.ACTION_REJECT, task.reject_reason)
                messages.warning(request, 'Đã từ chối công việc. Cấp trên có thể giao lại cho người khác.')
                return redirect('tasks:detail', pk=pk)

        if action == 'progress' and is_assignee and task.status in {
            WorkTask.STATUS_IN_PROGRESS, WorkTask.STATUS_REVISION,
        }:
            progress_form = WorkTaskProgressForm(request.POST)
            if progress_form.is_valid():
                task.progress_percent = progress_form.cleaned_data['progress_percent']
                task.result_note = progress_form.cleaned_data['result_note']
                task.save(update_fields=['progress_percent', 'result_note', 'updated_at'])
                log_task_action(
                    task, request.user, WorkTaskLog.ACTION_PROGRESS,
                    f'Tiến độ {task.progress_percent}%',
                )
                messages.success(request, 'Đã cập nhật tiến độ.')
                return redirect('tasks:detail', pk=pk)

        if action == 'submit' and is_assignee and task.status in {
            WorkTask.STATUS_IN_PROGRESS, WorkTask.STATUS_REVISION,
        }:
            submit_form = WorkTaskSubmitForm(request.POST)
            if submit_form.is_valid():
                task.status = WorkTask.STATUS_PENDING_REVIEW
                task.result_note = submit_form.cleaned_data['result_note']
                task.progress_percent = max(task.progress_percent, 100)
                task.submitted_at = timezone.now()
                task.save(update_fields=[
                    'status', 'result_note', 'progress_percent', 'submitted_at', 'updated_at',
                ])
                log_task_action(task, request.user, WorkTaskLog.ACTION_SUBMIT, task.result_note)
                messages.success(request, 'Đã nộp chờ cấp trên duyệt.')
                return redirect('tasks:detail', pk=pk)

        if action == 'approve' and is_assigner and task.status == WorkTask.STATUS_PENDING_REVIEW:
            review_form = WorkTaskReviewForm(request.POST)
            if review_form.is_valid():
                task.status = WorkTask.STATUS_COMPLETED
                task.review_note = review_form.cleaned_data['review_note']
                task.completed_at = timezone.now()
                task.progress_percent = 100
                task.save(update_fields=[
                    'status', 'review_note', 'completed_at', 'progress_percent', 'updated_at',
                ])
                log_task_action(task, request.user, WorkTaskLog.ACTION_APPROVE, task.review_note)
                if task.project_id:
                    unlocked = unlock_dependent_steps(task)
                    if unlocked:
                        messages.info(
                            request,
                            f'Đã mở {len(unlocked)} bước phụ thuộc.',
                        )
                messages.success(request, 'Đã duyệt hoàn thành công việc.')
                return redirect('tasks:detail', pk=pk)

        if action == 'revision' and is_assigner and task.status == WorkTask.STATUS_PENDING_REVIEW:
            review_form = WorkTaskReviewForm(request.POST)
            if review_form.is_valid() and review_form.cleaned_data['review_note'].strip():
                task.status = WorkTask.STATUS_REVISION
                task.review_note = review_form.cleaned_data['review_note']
                task.save(update_fields=['status', 'review_note', 'updated_at'])
                log_task_action(task, request.user, WorkTaskLog.ACTION_REVISION, task.review_note)
                messages.info(request, 'Đã yêu cầu nhân viên sửa lại.')
                return redirect('tasks:detail', pk=pk)
            messages.error(request, 'Vui lòng nhập ghi chú khi yêu cầu sửa.')

        if action == 'cancel' and is_assigner and task.status not in {
            WorkTask.STATUS_COMPLETED, WorkTask.STATUS_CANCELLED, WorkTask.STATUS_REASSIGNED,
        }:
            task.status = WorkTask.STATUS_CANCELLED
            task.save(update_fields=['status', 'updated_at'])
            log_task_action(task, request.user, WorkTaskLog.ACTION_CANCEL, 'Hủy công việc')
            messages.info(request, 'Đã hủy công việc.')
            return redirect('tasks:assigned')

    batch_siblings = None
    if task.assignment_batch:
        batch_siblings = WorkTask.objects.filter(
            assignment_batch=task.assignment_batch,
        ).exclude(pk=task.pk).select_related('assignee', 'assignee__profile')[:10]

    pending_handoff = None
    can_request_handoff = False
    if task.project_id and is_assignee and task.status in {
        WorkTask.STATUS_IN_PROGRESS, WorkTask.STATUS_REVISION,
    }:
        pending_handoff = task.handoff_requests.filter(
            status=WorkTaskHandoff.STATUS_PENDING,
        ).select_related('to_user', 'to_user__profile').first()
        can_request_handoff = pending_handoff is None

    attachments = _task_attachments(task)
    assign_attachments = attachments.filter(stage=WorkTaskAttachment.STAGE_ASSIGN)
    work_attachments = attachments.filter(stage=WorkTaskAttachment.STAGE_WORK)
    assign_images, assign_files = _split_attachments(assign_attachments)
    work_images, work_files = _split_attachments(work_attachments)

    return render(request, 'tasks/detail.html', {
        'task': task,
        'project': task.project,
        'logs': task.logs.select_related('actor', 'actor__profile'),
        'assign_images': assign_images,
        'assign_files': assign_files,
        'work_images': work_images,
        'work_files': work_files,
        'can_upload_work': is_assignee and task.status in ASSIGNEE_UPLOAD_STATUSES,
        'is_assignee': is_assignee,
        'is_assigner': is_assigner,
        'can_assign': can_assign_tasks(request.user),
        'can_request_handoff': can_request_handoff,
        'pending_handoff': pending_handoff,
        'progress_form': progress_form,
        'submit_form': submit_form,
        'reject_form': reject_form,
        'review_form': review_form,
        'batch_siblings': batch_siblings,
    })


@_assign_access_required
def reassign_task(request, pk):
    old_task = get_object_or_404(WorkTask, pk=pk, assigner=request.user)
    if old_task.status != WorkTask.STATUS_REJECTED:
        messages.error(request, 'Chỉ giao lại được khi nhân viên đã từ chối việc.')
        return redirect('tasks:detail', pk=pk)

    if request.method == 'POST':
        form = WorkTaskReassignForm(
            request.POST,
            assigner=request.user,
            exclude_user=old_task.assignee,
        )
        if form.is_valid():
            new_assignee = form.cleaned_data['assignee']
            new_task = WorkTask.objects.create(
                assignment_batch=old_task.assignment_batch,
                title=old_task.title,
                description=old_task.description,
                task_type=old_task.task_type,
                priority=old_task.priority,
                due_date=old_task.due_date,
                assigner=request.user,
                assignee=new_assignee,
                reassigned_from=old_task,
            )
            copy_task_attachments(
                old_task,
                new_task,
                stages=[WorkTaskAttachment.STAGE_ASSIGN],
                uploaded_by=request.user,
            )
            old_task.status = WorkTask.STATUS_REASSIGNED
            old_task.replaced_by = new_task
            old_task.save(update_fields=['status', 'replaced_by', 'updated_at'])
            log_task_action(
                old_task, request.user, WorkTaskLog.ACTION_REASSIGN,
                f'Giao lại cho {new_assignee.username}',
            )
            log_task_action(new_task, request.user, WorkTaskLog.ACTION_ASSIGNED, f'Giao lại từ #{old_task.pk}')
            messages.success(request, f'Đã giao lại cho {new_assignee.profile.full_name or new_assignee.username}.')
            return redirect('tasks:detail', pk=new_task.pk)
    else:
        form = WorkTaskReassignForm(
            assigner=request.user,
            exclude_user=old_task.assignee,
        )

    return render(request, 'tasks/reassign.html', {
        'form': form,
        'task': old_task,
    })
