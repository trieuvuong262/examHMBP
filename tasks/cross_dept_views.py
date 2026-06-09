import uuid

from django.contrib import messages
from django.db.models import Max, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_TASKS
from hrm.permissions import (
    can_administer_project,
    can_claim_cross_dept_step,
    can_create_cross_dept_project,
    can_manage_project,
    can_manage_project_steps,
    is_cross_dept_read_only_viewer,
)
from PortalJustPlay.list_search import apply_combined_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .cross_dept_forms import CrossDeptProjectForm, CrossDeptStepForm
from .cross_dept_utils import (
    cross_dept_projects_for_user,
    ensure_project_member,
    initial_cross_dept_step_status,
    pending_claim_count_for_user,
    pending_claim_steps_for_user,
)
from .models import InternalProject, ProjectComment, WorkTask, WorkTaskHandoff, WorkTaskLog
from .project_forms import ProjectCommentForm
from .project_utils import build_mention_member_list, render_comment_body_html, resolve_project_mentions
from .project_views import _get_project_or_404
from .utils import log_task_action
from .views import _get_task_or_404, _redirect_task_detail, _tasks_access_required


def _get_cross_dept_project_or_404(user, pk):
    project = get_object_or_404(
        InternalProject.objects.filter(project_type=InternalProject.TYPE_CROSS_DEPT)
        .select_related('owner', 'owner__profile')
        .prefetch_related('departments'),
        pk=pk,
    )
    if not _get_project_or_404(user, pk):
        return None
    return project


@_tasks_access_required
def cross_dept_list(request):
    search_query = get_search_query(request)
    qs = cross_dept_projects_for_user(request.user).select_related(
        'owner', 'owner__profile',
    ).prefetch_related('departments')
    qs = apply_combined_search(qs, search_query, lambda term: (
        Q(title__icontains=term)
        | Q(description__icontains=term)
        | Q(owner__username__icontains=term)
        | Q(owner__profile__full_name__icontains=term)
        | Q(departments__name__icontains=term)
    ))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'tasks/cross_dept_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'can_create': can_create_cross_dept_project(request.user),
        'pending_claim_count': pending_claim_count_for_user(request.user),
    })


@module_perm_required(MODULE_TASKS, 'create')
def cross_dept_create(request):
    if not can_create_cross_dept_project(request.user):
        messages.error(request, 'Chỉ Giám đốc hoặc Trưởng bộ phận mới tạo được dự án liên phòng ban.')
        return redirect('tasks:cross_dept_list')

    if request.method == 'POST':
        form = CrossDeptProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.owner = request.user
            project.project_type = InternalProject.TYPE_CROSS_DEPT
            project.status = InternalProject.STATUS_ACTIVE
            project.save()
            form.save_m2m()
            ensure_project_member(project, request.user)
            messages.success(
                request,
                f'Đã tạo dự án liên phòng ban «{project.title}». Thêm bước công việc để bắt đầu.',
            )
            return redirect('tasks:cross_dept_detail', pk=project.pk)
    else:
        form = CrossDeptProjectForm()

    return render(request, 'tasks/cross_dept_form.html', {
        'form': form,
        'is_create': True,
        'can_create': True,
    })


@_tasks_access_required
def cross_dept_pending(request):
    steps = pending_claim_steps_for_user(request.user)
    return render(request, 'tasks/cross_dept_pending.html', {
        'steps': steps,
        'can_create': can_create_cross_dept_project(request.user),
        'pending_claim_count': steps.count(),
    })


@_tasks_access_required
def cross_dept_detail(request, pk):
    project = _get_cross_dept_project_or_404(request.user, pk)
    if project is None:
        messages.error(request, 'Không tìm thấy dự án hoặc bạn không có quyền xem.')
        return redirect('tasks:cross_dept_list')

    is_owner = can_manage_project(request.user, project)
    can_add_step = can_manage_project_steps(request.user, project)
    can_administer = can_administer_project(request.user, project)
    is_read_only = is_cross_dept_read_only_viewer(request.user, project)
    can_comment = not is_read_only
    comment_form = ProjectCommentForm() if can_comment else None
    step_form = CrossDeptStepForm(project=project) if can_add_step else None
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

        if action == 'comment' and can_comment:
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
                return redirect('tasks:cross_dept_detail', pk=pk)

        if action == 'add_step' and can_add_step:
            step_form = CrossDeptStepForm(request.POST, project=project)
            if step_form.is_valid():
                depends_on = step_form.cleaned_data.get('depends_on')
                assignee_mode = step_form.cleaned_data['assignee_mode']
                assignee = step_form.cleaned_data.get('assignee')
                target_department = step_form.cleaned_data['target_department']
                max_order = project.steps.aggregate(m=Max('step_order'))['m'] or 0
                status = initial_cross_dept_step_status(depends_on, assignee_mode)
                step = WorkTask.objects.create(
                    assignment_batch=uuid.uuid4(),
                    title=step_form.cleaned_data['title'],
                    description=step_form.cleaned_data['description'],
                    task_type=WorkTask.TYPE_GENERAL,
                    priority=step_form.cleaned_data['priority'],
                    due_date=step_form.cleaned_data['due_date'],
                    assigner=project.owner,
                    assignee=assignee,
                    assignee_mode=assignee_mode,
                    target_department=target_department,
                    project=project,
                    depends_on=depends_on,
                    step_order=max_order + 1,
                    status=status,
                )
                if assignee:
                    ensure_project_member(project, assignee)
                    log_msg = f'Bước dự án → {assignee.username}'
                else:
                    log_msg = f'Bước dự án → hàng đợi {target_department.name}'
                log_task_action(step, request.user, WorkTaskLog.ACTION_ASSIGNED, log_msg)
                messages.success(request, f'Đã thêm bước «{step.title}».')
                return redirect('tasks:cross_dept_detail', pk=pk)

        if action == 'approve_handoff' and can_administer:
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
                return redirect('tasks:cross_dept_detail', pk=pk)

            new_task = WorkTask.objects.create(
                assignment_batch=uuid.uuid4(),
                title=source.title,
                description=source.description,
                task_type=source.task_type,
                priority=source.priority,
                due_date=source.due_date,
                assigner=project.owner,
                assignee=handoff.to_user,
                assignee_mode=WorkTask.ASSIGNEE_SPECIFIC,
                target_department=source.target_department,
                project=project,
                depends_on=source.depends_on,
                step_order=source.step_order,
                status=initial_cross_dept_step_status(source.depends_on, WorkTask.ASSIGNEE_SPECIFIC),
            )
            ensure_project_member(project, handoff.to_user)
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
            messages.success(
                request,
                f'Đã duyệt chuyển giao cho {handoff.to_user.profile.full_name or handoff.to_user.username}.',
            )
            return redirect('tasks:cross_dept_detail', pk=pk)

        if action == 'reject_handoff' and can_administer:
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
            return redirect('tasks:cross_dept_detail', pk=pk)

        if action == 'complete_project' and can_administer:
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
            return redirect('tasks:cross_dept_detail', pk=pk)

    steps = project.steps.select_related(
        'assignee', 'assignee__profile', 'depends_on', 'target_department',
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
    departments = project.departments.order_by('sort_order', 'name')
    claimable_step_ids = {
        step.pk for step in steps
        if can_claim_cross_dept_step(request.user, step)
    }

    return render(request, 'tasks/cross_dept_detail.html', {
        'project': project,
        'departments': departments,
        'steps': steps,
        'comment_items': comment_items,
        'comment_form': comment_form,
        'step_form': step_form,
        'members': members,
        'mention_members': build_mention_member_list(project),
        'is_owner': is_owner,
        'can_add_step': can_add_step,
        'can_administer': can_administer,
        'is_read_only': is_read_only,
        'can_comment': can_comment,
        'can_create': can_create_cross_dept_project(request.user),
        'pending_handoffs': pending_handoffs,
        'pending_claim_count': pending_claim_count_for_user(request.user),
        'claimable_step_ids': claimable_step_ids,
    })


@_tasks_access_required
def claim_cross_dept_step(request, pk):
    task = _get_task_or_404(request.user, pk)
    if task is None or not task.project_id or not task.project.is_cross_department:
        messages.error(request, 'Không tìm thấy bước công việc.')
        return redirect('tasks:cross_dept_pending')

    if not can_claim_cross_dept_step(request.user, task):
        messages.error(request, 'Bạn không thể tiếp nhận bước này.')
        return _redirect_task_detail(task)

    if request.method == 'POST':
        task.assignee = request.user
        task.status = WorkTask.STATUS_PENDING_ACK
        task.save(update_fields=['assignee', 'status', 'updated_at'])
        ensure_project_member(task.project, request.user)
        log_task_action(
            task,
            request.user,
            WorkTaskLog.ACTION_ASSIGNED,
            f'{request.user.username} tiếp nhận từ hàng đợi {task.target_department.name}',
        )
        messages.success(request, 'Đã tiếp nhận bước công việc. Vui lòng xác nhận và bắt đầu thực hiện.')
        return _redirect_task_detail(task)

    return render(request, 'tasks/cross_dept_claim.html', {
        'task': task,
        'project': task.project,
        'can_create': can_create_cross_dept_project(request.user),
    })
