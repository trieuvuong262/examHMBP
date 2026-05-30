import uuid

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from hrm.permissions import (
    can_create_internal_project,
    can_manage_project,
    can_receive_assigned_tasks,
    can_view_project,
)
from PortalJustPlay.list_search import apply_combined_search, apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .models import InternalProject, ProjectComment, WorkTask, WorkTaskAttachment, WorkTaskHandoff, WorkTaskLog
from .project_forms import (
    HandoffRequestForm,
    InternalProjectForm,
    ProjectCommentForm,
    ProjectStepForm,
    ProjectStepReassignForm,
)
from .project_utils import (
    build_mention_member_list,
    initial_step_status,
    render_comment_body_html,
    resolve_project_mentions,
)
from .attachment_utils import copy_task_attachments
from .cross_dept_utils import ensure_project_member
from .utils import log_task_action
from .views import _get_task_or_404, _project_detail_route, _redirect_task_detail, _task_detail_route, _tasks_access_required


def _get_project_or_404(user, pk):
    project = get_object_or_404(
        InternalProject.objects.select_related('owner', 'owner__profile'),
        pk=pk,
    )
    if not can_view_project(user, project):
        return None
    return project


@_tasks_access_required
def project_list(request):
    search_query = get_search_query(request)
    qs = InternalProject.objects.filter(
        project_type=InternalProject.TYPE_TEAM,
    ).filter(
        Q(owner=request.user) | Q(members=request.user),
    ).distinct().select_related('owner', 'owner__profile').prefetch_related('members')
    qs = apply_combined_search(qs, search_query, lambda term: (
        Q(title__icontains=term)
        | Q(description__icontains=term)
        | Q(owner__username__icontains=term)
        | Q(owner__profile__full_name__icontains=term)
    ))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'tasks/project_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'can_create': can_create_internal_project(request.user),
    })


@_tasks_access_required
def project_create(request):
    if not can_create_internal_project(request.user):
        messages.error(request, 'Chỉ Tổ trưởng hoặc Trưởng bộ phận (có quyền giao việc) mới tạo được dự án.')
        return redirect('tasks:project_list')

    if request.method == 'POST':
        form = InternalProjectForm(request.POST, owner=request.user)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.project_type = InternalProject.TYPE_TEAM
            project.status = InternalProject.STATUS_ACTIVE
            project.save()
            form.save_m2m()
            messages.success(request, f'Đã tạo dự án «{project.title}». Thêm bước công việc để bắt đầu.')
            return redirect('tasks:project_detail', pk=project.pk)
    else:
        form = InternalProjectForm(owner=request.user)

    return render(request, 'tasks/project_form.html', {
        'form': form,
        'is_create': True,
        'can_create': True,
    })


@_tasks_access_required
def project_detail(request, pk):
    project = _get_project_or_404(request.user, pk)
    if project is None:
        messages.error(request, 'Không tìm thấy dự án hoặc bạn không có quyền xem.')
        return redirect('tasks:project_list')

    is_owner = can_manage_project(request.user, project)
    comment_form = ProjectCommentForm()
    step_form = ProjectStepForm(project=project) if is_owner else None
    pending_handoffs = []

    if is_owner:
        pending_handoffs = list(
            project.handoffs.filter(status=WorkTaskHandoff.STATUS_PENDING).select_related(
                'source_task', 'from_user', 'from_user__profile',
                'to_user', 'to_user__profile', 'requested_by', 'requested_by__profile',
            ),
        )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'comment':
            comment_form = ProjectCommentForm(request.POST)
            if comment_form.is_valid():
                body = comment_form.cleaned_data['body'].strip()
                if body:
                    members = list(project.members.select_related('profile'))
                    mentioned, _ = resolve_project_mentions(body, members)
                    comment = ProjectComment.objects.create(
                        project=project,
                        author=request.user,
                        body=body,
                    )
                    if mentioned:
                        comment.mentioned_users.set(mentioned)
                    messages.success(request, 'Đã gửi comment.')
                return redirect('tasks:project_detail', pk=pk)

        if action == 'add_step' and is_owner:
            step_form = ProjectStepForm(request.POST, project=project)
            if step_form.is_valid():
                from django.db.models import Max

                depends_on = step_form.cleaned_data.get('depends_on')
                max_order = project.steps.aggregate(m=Max('step_order'))['m'] or 0
                status = initial_step_status(depends_on)
                step = WorkTask.objects.create(
                    assignment_batch=uuid.uuid4(),
                    title=step_form.cleaned_data['title'],
                    description=step_form.cleaned_data['description'],
                    task_type=WorkTask.TYPE_GENERAL,
                    priority=step_form.cleaned_data['priority'],
                    due_date=step_form.cleaned_data['due_date'],
                    assigner=project.owner,
                    assignee=step_form.cleaned_data['assignee'],
                    project=project,
                    depends_on=depends_on,
                    step_order=max_order + 1,
                    status=status,
                )
                log_task_action(
                    step, request.user, WorkTaskLog.ACTION_ASSIGNED,
                    f'Bước dự án → {step.assignee.username if step.assignee_id else "?"}',
                )
                messages.success(request, f'Đã thêm bước «{step.title}».')
                return redirect('tasks:project_detail', pk=pk)

        if action == 'approve_handoff' and is_owner:
            handoff_id = request.POST.get('handoff_id')
            handoff = get_object_or_404(
                WorkTaskHandoff,
                pk=handoff_id,
                project=project,
                status=WorkTaskHandoff.STATUS_PENDING,
            )
            source = handoff.source_task
            if source.status not in {
                WorkTask.STATUS_IN_PROGRESS,
                WorkTask.STATUS_PENDING_REVIEW,
                WorkTask.STATUS_REVISION,
            }:
                messages.error(request, 'Bước nguồn không còn trạng thái phù hợp để chuyển giao.')
                return redirect('tasks:project_detail', pk=pk)

            new_task = WorkTask.objects.create(
                assignment_batch=uuid.uuid4(),
                title=source.title,
                description=source.description,
                task_type=source.task_type,
                priority=source.priority,
                due_date=source.due_date,
                assigner=project.owner,
                assignee=handoff.to_user,
                project=project,
                depends_on=source.depends_on,
                step_order=source.step_order,
                status=initial_step_status(source.depends_on),
            )
            source.status = WorkTask.STATUS_HANDED_OFF
            source.save(update_fields=['status', 'updated_at'])
            log_task_action(
                source, request.user, WorkTaskLog.ACTION_HANDOFF,
                f'Chuyển giao cho {handoff.to_user.username}',
            )
            log_task_action(
                new_task, request.user, WorkTaskLog.ACTION_ASSIGNED,
                f'Nhận chuyển giao từ {handoff.from_user.username}',
            )
            handoff.status = WorkTaskHandoff.STATUS_APPROVED
            handoff.reviewed_by = request.user
            handoff.reviewed_at = timezone.now()
            handoff.created_task = new_task
            handoff.save(update_fields=[
                'status', 'reviewed_by', 'reviewed_at', 'created_task',
            ])
            messages.success(request, f'Đã duyệt chuyển giao cho {handoff.to_user.profile.full_name or handoff.to_user.username}.')
            return redirect('tasks:project_detail', pk=pk)

        if action == 'reject_handoff' and is_owner:
            handoff_id = request.POST.get('handoff_id')
            handoff = get_object_or_404(
                WorkTaskHandoff,
                pk=handoff_id,
                project=project,
                status=WorkTaskHandoff.STATUS_PENDING,
            )
            handoff.status = WorkTaskHandoff.STATUS_REJECTED
            handoff.reviewed_by = request.user
            handoff.reviewed_at = timezone.now()
            handoff.review_note = (request.POST.get('review_note') or '').strip()
            handoff.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_note'])
            messages.info(request, 'Đã từ chối yêu cầu chuyển giao.')
            return redirect('tasks:project_detail', pk=pk)

        if action == 'complete_project' and is_owner:
            open_steps = project.steps.exclude(
                status__in={
                    WorkTask.STATUS_COMPLETED,
                    WorkTask.STATUS_CANCELLED,
                    WorkTask.STATUS_HANDED_OFF,
                    WorkTask.STATUS_REASSIGNED,
                },
            ).exists()
            if open_steps:
                messages.error(request, 'Còn bước chưa hoàn thành — không thể đóng dự án.')
            else:
                project.status = InternalProject.STATUS_COMPLETED
                project.save(update_fields=['status', 'updated_at'])
                messages.success(request, 'Đã đánh dấu dự án hoàn thành.')
            return redirect('tasks:project_detail', pk=pk)

    steps = project.steps.select_related(
        'assignee', 'assignee__profile', 'depends_on',
        'reassigned_from', 'reassigned_from__assignee', 'reassigned_from__assignee__profile',
        'replaced_by',
    ).order_by('step_order', 'created_at')
    comments = project.comments.select_related(
        'author', 'author__profile',
    ).prefetch_related(
        Prefetch('mentioned_users', queryset=project.members.select_related('profile')),
    )
    comment_items = [
        {'comment': c, 'body_html': render_comment_body_html(c.body)}
        for c in comments
    ]
    members = project.members.select_related('profile').order_by('profile__full_name', 'username')

    return render(request, 'tasks/project_detail.html', {
        'project': project,
        'steps': steps,
        'comment_items': comment_items,
        'comment_form': comment_form,
        'step_form': step_form,
        'members': members,
        'mention_members': build_mention_member_list(project),
        'is_owner': is_owner,
        'can_create': can_create_internal_project(request.user),
        'pending_handoffs': pending_handoffs,
    })


@_tasks_access_required
def reassign_project_step(request, pk):
    old_task = get_object_or_404(
        WorkTask.objects.select_related(
            'project', 'assignee', 'assignee__profile', 'depends_on',
        ),
        pk=pk,
        project__isnull=False,
    )
    project = old_task.project
    step_route = _task_detail_route(old_task)
    if not can_manage_project(request.user, project):
        messages.error(request, 'Chỉ chủ dự án mới giao lại bước cho người khác.')
        return redirect(step_route, pk=pk)

    if old_task.status != WorkTask.STATUS_REJECTED:
        messages.error(request, 'Chỉ giao lại được khi nhân viên đã từ chối bước này.')
        return redirect(step_route, pk=pk)

    rejected_user = old_task.assignee
    if request.method == 'POST':
        form = ProjectStepReassignForm(
            request.POST,
            project=project,
            exclude_user=rejected_user,
        )
        if form.is_valid():
            new_assignee = form.cleaned_data['assignee']
            new_task = WorkTask.objects.create(
                assignment_batch=uuid.uuid4(),
                title=old_task.title,
                description=old_task.description,
                task_type=old_task.task_type,
                priority=old_task.priority,
                due_date=old_task.due_date,
                assigner=project.owner,
                assignee=new_assignee,
                assignee_mode=old_task.assignee_mode,
                target_department=old_task.target_department,
                project=project,
                depends_on=old_task.depends_on,
                step_order=old_task.step_order,
                status=initial_step_status(old_task.depends_on),
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
            ensure_project_member(project, new_assignee)
            rejected_name = rejected_user.profile.full_name or rejected_user.username
            log_task_action(
                old_task, request.user, WorkTaskLog.ACTION_REASSIGN,
                f'Giao lại cho {new_assignee.username} (từ chối bởi {rejected_name})',
            )
            log_task_action(
                new_task, request.user, WorkTaskLog.ACTION_ASSIGNED,
                f'Nhận bước thay thế — từ chối bởi {rejected_name}',
            )
            messages.success(
                request,
                f'Đã giao bước cho {new_assignee.profile.full_name or new_assignee.username}. '
                f'Vẫn lưu vết {rejected_name} đã từ chối.',
            )
            return redirect('tasks:project_step', pk=new_task.pk)
    else:
        form = ProjectStepReassignForm(
            project=project,
            exclude_user=rejected_user,
        )

    return render(request, 'tasks/project_reassign.html', {
        'form': form,
        'task': old_task,
        'project': project,
        'rejected_user': rejected_user,
        'can_create': can_create_internal_project(request.user),
    })


@_tasks_access_required
def request_handoff(request, pk):
    task = _get_task_or_404(request.user, pk)
    if task is None or not task.project_id:
        messages.error(request, 'Không thể chuyển giao việc này.')
        return redirect('tasks:project_list')

    project = task.project
    step_route = _task_detail_route(task)
    detail_route = _project_detail_route(project)
    is_assignee = (
        task.assignee_id == request.user.id
        and can_receive_assigned_tasks(request.user)
    )
    if not is_assignee:
        messages.error(request, 'Chỉ người đang phụ trách mới yêu cầu chuyển giao.')
        return redirect(step_route, pk=pk)

    if task.status not in {
        WorkTask.STATUS_IN_PROGRESS,
        WorkTask.STATUS_REVISION,
    }:
        messages.error(request, 'Chỉ chuyển giao khi đang thực hiện hoặc cần sửa.')
        return redirect(step_route, pk=pk)

    if task.handoff_requests.filter(status=WorkTaskHandoff.STATUS_PENDING).exists():
        messages.info(request, 'Đã có yêu cầu chuyển giao đang chờ duyệt.')
        return redirect(step_route, pk=pk)

    if request.method == 'POST':
        form = HandoffRequestForm(
            request.POST,
            project=project,
            exclude_user=request.user,
        )
        if form.is_valid():
            WorkTaskHandoff.objects.create(
                project=project,
                source_task=task,
                from_user=request.user,
                to_user=form.cleaned_data['to_user'],
                requested_by=request.user,
                note=form.cleaned_data['note'],
            )
            log_task_action(
                task, request.user, WorkTaskLog.ACTION_HANDOFF,
                f'Yêu cầu chuyển giao → {form.cleaned_data["to_user"].username}',
            )
            messages.success(request, 'Đã gửi yêu cầu chuyển giao — chờ chủ dự án duyệt.')
            return redirect(detail_route, pk=project.pk)
    else:
        form = HandoffRequestForm(project=project, exclude_user=request.user)

    return render(request, 'tasks/handoff_request.html', {
        'form': form,
        'task': task,
        'project': project,
        'can_create': can_create_internal_project(request.user),
    })
