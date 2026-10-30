from __future__ import annotations

import calendar as cal
from collections import OrderedDict
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from hrm.menu_permissions import handle_menu_access_denied, user_can_access_resolved_menu
from PortalJustPlay.pagination import paginate_queryset
from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context
from thiet_ke_sp import catalog
from thiet_ke_sp.presenters import cover_map

from . import forms as f
from . import permissions as perms
from . import services as svc
from .context_processors import invalidate_plan_badges
from .defaults import load_default_checklist
from .list_grid import LIST_KEY
from .models import (
    APPROVAL_STATUSES,
    FINAL_STATUSES,
    GROUP_WEIGHTS,
    OPEN_TASK_STATUSES,
    ChecklistTemplateItem,
    Decision,
    LaunchGroupDefault,
    LaunchPlan,
    LaunchPlanGroupOwner,
    LaunchPlanProduct,
    LaunchRisk,
    LaunchTask,
    LaunchTaskFile,
    PostLaunchReview,
    RiskSeverity,
    Status,
    TaskGroup,
    TaskStatus,
    milestone_label,
)

M = perms.M

TABS = (
    ('overview', 'Tổng quan', 'bi-info-circle'),
    ('products', 'Sản phẩm', 'bi-bag'),
    ('timeline', 'Mốc tiến độ', 'bi-calendar-week'),
    ('production', 'Sản xuất và tồn kho', 'bi-gear-wide-connected'),
    ('marketing', 'Marketing', 'bi-camera-video'),
    ('sales', 'Kinh doanh và kênh bán', 'bi-shop'),
    ('budget', 'Ngân sách', 'bi-cash-stack'),
    ('go', 'Go/No-Go', 'bi-flag'),
    ('post', 'Sau ra mắt', 'bi-graph-up-arrow'),
    ('history', 'Lịch sử thao tác', 'bi-clock-history'),
)
TAB_KEYS = {t[0] for t in TABS}
TAB_GROUPS = {
    'production': (TaskGroup.PRODUCTION, TaskGroup.LOGISTICS),
    'marketing': (TaskGroup.MARKETING,),
    'sales': (TaskGroup.PRICE, TaskGroup.CHANNEL),
    'budget': (TaskGroup.PRICE, TaskGroup.MARKETING, TaskGroup.APPROVAL),
}

QUICK_FILTERS = (
    ('', 'Đang chạy'),
    ('risk', 'Có rủi ro'),
    ('pending', 'Chờ quyết định'),
    ('launched', 'Đã ra mắt'),
    ('draft', 'Nháp'),
    ('closed', 'Hoàn tất / dừng / hủy'),
    ('all', 'Tất cả'),
)
ACTIVE_STATUSES = (
    Status.PLAN_PENDING, Status.PREPARING, Status.AT_RISK, Status.LAUNCH_PENDING, Status.READY,
    Status.LAUNCHED, Status.REVIEWING,
)


def _deny(request, menu: str):
    return handle_menu_access_denied(request, M, menu)


def _common(request, **extra):
    user = request.user
    ctx = {
        'rm_can_create': perms.can_create(user),
        'rm_can_settings': perms.can_manage_settings(user),
    }
    ctx.update(extra)
    return ctx


def _plan_qs():
    return LaunchPlan.objects.select_related('coordinator__profile', 'approver__profile', 'created_by__profile')


def _visible_plans(user):
    qs = _plan_qs()
    if perms.can_view_module(user):
        return qs
    return qs.filter(pk__in=perms.participant_plan_ids(user))


def _decorate(plans: list[LaunchPlan]) -> list[LaunchPlan]:
    """Gắn % sẵn sàng, màu cảnh báo, số sản phẩm cho danh sách kế hoạch."""
    ids = [p.pk for p in plans]
    tasks: dict[int, list] = {}
    for t in LaunchTask.objects.filter(plan_id__in=ids):
        tasks.setdefault(t.plan_id, []).append(t)
    high_risks: dict[int, list] = {}
    for plan_id, desc in LaunchRisk.objects.filter(
        plan_id__in=ids, state=LaunchRisk.STATE_OPEN, severity=RiskSeverity.HIGH,
    ).values_list('plan_id', 'description'):
        high_risks.setdefault(plan_id, []).append((desc or '')[:80])
    high = {k: len(v) for k, v in high_risks.items()}
    products: dict[int, list] = {}
    for link in LaunchPlanProduct.objects.filter(plan_id__in=ids).select_related('dossier', 'style'):
        link.dossier.style_code = link.style.code if link.style_id else ''
        products.setdefault(link.plan_id, []).append(link.dossier)
    covers = cover_map([d.pk for ds in products.values() for d in ds])
    for p in plans:
        p.ready = svc.readiness(p, tasks.get(p.pk, []))
        p.high_risks = high.get(p.pk, 0)
        p.tone = svc.tone(p, p.ready, p.high_risks)
        p.tone_label = svc.TONE_LABELS[p.tone]
        p.dossiers = products.get(p.pk, [])
        p.groups = sorted({catalog.group_label(d.product_group) for d in p.dossiers if d.product_group})
        p.cover = next((covers[d.pk] for d in p.dossiers if d.pk in covers), None)
        p.collections = sorted({(d.collection or '').strip() for d in p.dossiers} - {''})
        p.blocking = _blocking_issues(p, tasks.get(p.pk, []), high_risks.get(p.pk, []))
    return plans


def _blocking_issues(plan: LaunchPlan, tasks: list, high_risks: list) -> list[str]:
    """Vấn đề đang chặn: việc «Vướng mắc», điều kiện Go trễ hạn, rủi ro mức Cao đang mở."""
    if plan.status in FINAL_STATUSES:
        return []
    today = timezone.localdate()
    issues = [f'Vướng: {t.title}' for t in tasks if t.status == TaskStatus.BLOCKED]
    issues += [
        f'Điều kiện Go trễ: {t.title}' for t in tasks
        if t.is_go_blocker and t.status in OPEN_TASK_STATUSES and t.status != TaskStatus.BLOCKED and t.due_date < today
    ]
    issues += [f'Rủi ro cao: {r}' for r in high_risks]
    return issues


def _refresh_running(plans) -> None:
    for p in plans:
        if p.status in (Status.PREPARING, Status.AT_RISK):
            svc.refresh_risk(p)


# ---------------------------------------------------------------------------
# Tổng quan
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_DASHBOARD):
        return _deny(request, perms.MENU_DASHBOARD)
    today = timezone.localdate()
    try:
        horizon = int(request.GET.get('horizon') or 90)
    except (TypeError, ValueError):
        horizon = 90
    if horizon not in (30, 60, 90, 120):
        horizon = 90
    running = list(_visible_plans(user).filter(status__in=ACTIVE_STATUSES))
    _refresh_running(running)
    running = _decorate(list(_visible_plans(user).filter(status__in=ACTIVE_STATUSES)))
    upcoming = [p for p in running if p.status not in (Status.LAUNCHED, Status.REVIEWING)]
    upcoming.sort(key=lambda p: p.launch_date)
    window = [p for p in upcoming if 0 <= p.days_to_launch <= horizon]
    open_tasks = LaunchTask.objects.filter(plan__in=[p.pk for p in running], status__in=OPEN_TASK_STATUSES)
    overdue = list(open_tasks.filter(due_date__lt=today).select_related('plan', 'owner__profile').order_by('due_date')[:8])
    risks = list(
        LaunchRisk.objects.filter(plan__in=[p.pk for p in running], state=LaunchRisk.STATE_OPEN)
        .select_related('plan', 'owner__profile').order_by('severity', 'due_date')[:6]
    )
    reviews_due = list(
        PostLaunchReview.objects.filter(
            plan__status__in=(Status.LAUNCHED, Status.REVIEWING), submitted_at__isnull=True, due_date__lte=today,
            plan__in=[p.pk for p in running],
        ).select_related('plan')
    )
    pending_plans = [p for p in running if p.status in APPROVAL_STATUSES]
    kpi = {
        'next_n': len(window),
        'horizon': horizon,
        'at_risk': sum(1 for p in running if p.tone == 'red'),
        'pending': len(pending_plans),
        'overdue': open_tasks.filter(due_date__lt=today).count(),
        'launched': sum(1 for p in running if p.status in (Status.LAUNCHED, Status.REVIEWING)),
        'avg_ready': round(sum(p.ready['pct'] for p in window) / len(window)) if window else None,
    }
    return render(request, 'ra_mat_sp/dashboard.html', _common(
        request, kpi=kpi, upcoming=window[:10], overdue=overdue, risks=risks, reviews_due=reviews_due,
        pending_plans=pending_plans[:6], horizon=horizon, rm_active='dashboard',
    ))


# ---------------------------------------------------------------------------
# Danh sách
# ---------------------------------------------------------------------------

@login_required
def plan_list(request):
    user = request.user
    qs = _visible_plans(user)
    g = request.GET
    quick = g.get('quick', '')
    if quick == 'risk':
        qs = qs.filter(status=Status.AT_RISK)
    elif quick == 'pending':
        qs = qs.filter(status__in=APPROVAL_STATUSES)
    elif quick == 'launched':
        qs = qs.filter(status__in=(Status.LAUNCHED, Status.REVIEWING))
    elif quick == 'draft':
        qs = qs.filter(status=Status.DRAFT)
    elif quick == 'closed':
        qs = qs.filter(status__in=(Status.DONE, Status.PAUSED, Status.CANCELLED))
    elif quick != 'all':
        qs = qs.filter(status__in=ACTIVE_STATUSES)
    q = (g.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(code__icontains=q) | Q(name__icontains=q) | Q(products__dossier__code__icontains=q)
            | Q(products__dossier__name__icontains=q) | Q(products__style__code__icontains=q)
            | Q(products__style__name__icontains=q)
        ).distinct()
    coordinator = g.get('coordinator') or ''
    if coordinator.isdigit():
        qs = qs.filter(coordinator_id=int(coordinator))
    group = g.get('group') or ''
    if group:
        qs = qs.filter(products__dossier__product_group=group).distinct()
    grid = sx_list_grid_context(request, LIST_KEY)
    if g.get('sort'):
        qs = apply_sx_list_sort(qs, request, LIST_KEY)
    else:
        qs = qs.order_by('launch_date', 'pk')
        grid['sort_dir'] = 'asc'
    page_obj, query_string = paginate_queryset(
        request, qs.select_related('coordinator__profile', 'approver__profile', 'created_by__profile'), per_page=30)
    plans = list(page_obj.object_list)
    _refresh_running(plans)
    plans = _decorate(plans)
    User = get_user_model()
    coordinators = User.objects.filter(
        pk__in=LaunchPlan.objects.values('coordinator_id')).select_related('profile').order_by('profile__full_name')
    return render(request, 'ra_mat_sp/plan_list.html', _common(
        request, plans=plans, page_obj=page_obj, query_string=query_string, quick=quick,
        quick_filters=QUICK_FILTERS, q=q,
        coordinators=[(u.pk, svc.display_name(u)) for u in coordinators], coordinator=coordinator,
        group_choices=catalog.group_choices(), group=group, rm_active='plans',
        has_filters=bool(q or coordinator or group), **grid,
    ))


# ---------------------------------------------------------------------------
# Lịch ra mắt
# ---------------------------------------------------------------------------

def _month_add(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


@login_required
def calendar_view(request):
    user = request.user
    today = timezone.localdate()
    view = request.GET.get('view') or 'quarter'
    if view not in ('month', 'quarter', 'year'):
        view = 'quarter'
    try:
        start = date.fromisoformat((request.GET.get('start') or '') + '-01') if request.GET.get('start') else None
    except ValueError:
        start = None
    if start is None:
        start = date(today.year, today.month, 1)
        if view == 'quarter':
            start = date(today.year, (today.month - 1) // 3 * 3 + 1, 1)
        elif view == 'year':
            start = date(today.year, 1, 1)
    span = {'month': 1, 'quarter': 3, 'year': 12}[view]
    end = _month_add(start, span)
    group = request.GET.get('group') or ''
    collection = (request.GET.get('collection') or '').strip()
    coordinator = request.GET.get('coordinator') or ''
    tone_filter = request.GET.get('tone') or ''
    qs = _visible_plans(user).filter(launch_date__gte=start, launch_date__lt=end).exclude(status=Status.CANCELLED)
    if group:
        qs = qs.filter(products__dossier__product_group=group).distinct()
    if collection:
        qs = qs.filter(products__dossier__collection__icontains=collection).distinct()
    if coordinator.isdigit():
        uid = int(coordinator)
        qs = qs.filter(Q(coordinator_id=uid) | Q(group_owners__owner_id=uid)).distinct()
    plans = _decorate(list(qs.order_by('launch_date')))
    if tone_filter:
        plans = [p for p in plans if p.tone == tone_filter]
    months = []
    for i in range(span):
        m_start = _month_add(start, i)
        m_plans = [p for p in plans if p.launch_date.year == m_start.year and p.launch_date.month == m_start.month]
        weeks = []
        if view == 'month':
            by_day: dict[int, list] = {}
            for p in m_plans:
                by_day.setdefault(p.launch_date.day, []).append(p)
            for week in cal.Calendar(firstweekday=0).monthdatescalendar(m_start.year, m_start.month):
                weeks.append([
                    {'date': d, 'in_month': d.month == m_start.month, 'is_today': d == today,
                     'plans': by_day.get(d.day, []) if d.month == m_start.month else []}
                    for d in week
                ])
        months.append({'start': m_start, 'plans': m_plans, 'weeks': weeks})
    nav = {
        'prev': _month_add(start, -span).strftime('%Y-%m'),
        'next': _month_add(start, span).strftime('%Y-%m'),
        'today': date(today.year, today.month, 1).strftime('%Y-%m'),
    }
    User = get_user_model()
    coordinators = User.objects.filter(
        Q(pk__in=LaunchPlan.objects.values('coordinator_id'))
        | Q(pk__in=LaunchPlanGroupOwner.objects.exclude(owner=None).values('owner_id'))
    ).select_related('profile').order_by('profile__full_name').distinct()
    filter_qs = urlencode({k: v for k, v in (
        ('group', group), ('coordinator', coordinator), ('tone', tone_filter), ('collection', collection),
    ) if v})
    collections = sorted({
        (c or '').strip()
        for c in LaunchPlanProduct.objects.exclude(dossier__collection='')
        .values_list('dossier__collection', flat=True).distinct()
        if (c or '').strip()
    })
    return render(request, 'ra_mat_sp/calendar.html', _common(
        request, months=months, view=view, start=start, end=end - timedelta(days=1), nav=nav,
        group=group, group_choices=catalog.group_choices(), collection=collection, collections=collections,
        coordinator=coordinator, coordinators=[(u.pk, svc.display_name(u)) for u in coordinators],
        tone=tone_filter, total=len(plans), rm_active='calendar', filter_qs=filter_qs,
        weekdays=('T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN'),
    ))


# ---------------------------------------------------------------------------
# Tạo / sửa / xóa
# ---------------------------------------------------------------------------

@login_required
def plan_create(request):
    user = request.user
    if not perms.can_create(user):
        return _deny(request, perms.MENU_PLANS)
    initial = {'coordinator': user.pk}
    style_code = (request.GET.get('style') or '').strip()
    if style_code:
        initial['styles'] = list(svc.library_styles().filter(code__iexact=style_code).values_list('pk', flat=True))
    form = f.PlanForm(request.POST or None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                plan = svc.create_plan(form.save(commit=False), list(form.cleaned_data['styles']), user)
        except svc.WorkflowError as exc:
            form.add_error('styles', str(exc))
        else:
            try:
                svc.assign_group_owners(plan, user, svc.parse_owner_map(request.POST))
            except svc.WorkflowError as exc:
                messages.error(request, str(exc))
            invalidate_plan_badges(plan)
            messages.success(request, f'Đã tạo kế hoạch {plan.code} và sinh checklist theo mốc T-/D+.')
            return redirect(f'{plan.get_absolute_url()}?tab=timeline')
    selected = dict(LaunchGroupDefault.objects.values_list('group', 'owner_id'))
    return render(request, 'ra_mat_sp/plan_form.html', _common(
        request, form=form, rm_active='create', title='Tạo kế hoạch ra mắt',
        back_url=reverse('ra_mat_sp:list'), owner_rows=f.owner_choice_rows(selected),
    ))


@login_required
def plan_edit(request, pk):
    user = request.user
    plan = get_object_or_404(_plan_qs(), pk=pk)
    if not perms.can_edit_header(plan, user):
        messages.error(request, 'Bạn không sửa được kế hoạch này ở trạng thái hiện tại.')
        return redirect(plan.get_absolute_url())
    old_date = plan.launch_date
    form = f.PlanForm(request.POST or None, instance=plan)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                svc.update_plan(form.save(commit=False), list(form.cleaned_data['styles']), user,
                                old_launch_date=old_date)
        except svc.WorkflowError as exc:
            form.add_error('styles', str(exc))
            plan.refresh_from_db()
        else:
            try:
                svc.assign_group_owners(plan, user, svc.parse_owner_map(request.POST))
            except svc.WorkflowError as exc:
                messages.error(request, str(exc))
            invalidate_plan_badges(plan)
            messages.success(request, 'Đã cập nhật kế hoạch.')
            return redirect(plan.get_absolute_url())
    svc.ensure_group_owners(plan)
    selected = dict(plan.group_owners.values_list('group', 'owner_id'))
    return render(request, 'ra_mat_sp/plan_form.html', _common(
        request, form=form, plan=plan, rm_active='edit', title=f'Sửa kế hoạch {plan.code}',
        back_url=plan.get_absolute_url(), owner_rows=f.owner_choice_rows(selected),
    ))


@login_required
@require_POST
def plan_delete(request, pk):
    plan = get_object_or_404(LaunchPlan, pk=pk)
    if not perms.can_delete_plan(plan, request.user):
        messages.error(request, 'Chỉ xóa được kế hoạch ở trạng thái Nháp.')
        return redirect(plan.get_absolute_url())
    code = plan.code
    plan.delete()
    messages.success(request, f'Đã xóa kế hoạch nháp {code}.')
    return redirect('ra_mat_sp:list')


# ---------------------------------------------------------------------------
# Chi tiết
# ---------------------------------------------------------------------------

def _timeline(tasks: list[LaunchTask]) -> list[dict]:
    buckets: OrderedDict[int, list] = OrderedDict()
    for t in sorted(tasks, key=lambda t: (t.offset_days, t.sort_order, t.pk)):
        buckets.setdefault(t.offset_days, []).append(t)
    rows = []
    for offset, items in buckets.items():
        done = sum(1 for t in items if t.status in (TaskStatus.DONE, TaskStatus.NA))
        rows.append({
            'label': milestone_label(offset), 'offset': offset, 'due': items[0].due_date, 'tasks': items,
            'done': done, 'total': len(items),
            'late': any(t.is_overdue for t in items),
        })
    return rows


@login_required
def plan_detail(request, pk):
    user = request.user
    plan = get_object_or_404(_plan_qs(), pk=pk)
    if not perms.can_view_plan(plan, user):
        return _deny(request, perms.MENU_PLANS)
    svc.refresh_risk(plan, None)
    tab = request.GET.get('tab') or 'overview'
    if tab not in TAB_KEYS:
        tab = 'overview'
    svc.ensure_group_owners(plan)
    tasks = list(plan.tasks.select_related('owner__profile', 'completed_by__profile').prefetch_related(
        'collaborators__profile', 'files'))
    can_edit = perms.can_edit_plan(plan, user)
    for t in tasks:
        t.can_update = perms.can_update_task(plan, t, user)
        t.mine = t.owner_id == user.pk
    ready = svc.readiness(plan, tasks)
    risks = list(plan.risks.select_related('owner__profile', 'created_by__profile'))
    high = sum(1 for r in risks if r.is_open and r.severity == RiskSeverity.HIGH)
    links = list(plan.products.select_related(
        'style__product_type',
        'dossier__owner__profile', 'dossier__designer__profile', 'dossier__handover',
        'dossier__approved_design_version', 'dossier__final_sample_version',
    ))
    covers = cover_map([l.dossier_id for l in links])
    official = {
        (l.style.code if l.style_id else (l.dossier.official_product_code or '')).strip().upper() for l in links
    } - {''}
    in_library = set()
    if official:
        from thiet_ke_sp.models import Handover, Status as HandoverStatus

        in_library = {
            (code or '').upper()
            for code in Handover.objects.filter(
                product_code__in=official,
                dossier__status__in=(HandoverStatus.HANDED_OVER, HandoverStatus.CLOSED),
            ).values_list('product_code', flat=True)
        }
    for link in links:
        link.cover = covers.get(link.dossier_id)
        link.library_code = (link.style.code if link.style_id else (link.dossier.official_product_code or '')).strip().upper()
        link.display_name = (link.style.name if link.style_id and link.style.name else link.dossier.name)
        link.in_library = link.library_code in in_library
        link.production_state = svc.production_state(link.dossier)
        link.production_label = svc.PRODUCTION_STATE_LABELS[link.production_state]
        link.group_label = catalog.group_label(link.dossier.product_group) if link.dossier.product_group else ''
    reviews = list(plan.reviews.select_related('submitted_by__profile'))
    for r in reviews:
        r.can_submit = can_edit and svc.can_review(plan, r)
        r.form = f.ReviewForm(instance=r, prefix=f'rv{r.pk}') if r.can_submit else None
    is_approver = perms.is_plan_approver(plan, user)
    plan_tone = svc.tone(plan, ready, high)
    go_rows = svc.go_conditions(plan, tasks, links)
    gap_keys = ('design_gap', 'lock_gap', 'price_gap', 'mo_gap', 'stock_gap', 'media_gap', 'channel_gap')
    for link in links:
        fact = getattr(link, 'fact', None)
        link.gap_total = len(gap_keys)
        link.gap_ok = sum(1 for k in gap_keys if fact is not None and not getattr(fact, k, ''))
    product_summary = {
        'count': len(links),
        'qty': sum(l.planned_qty or 0 for l in links),
        'ready': sum(1 for l in links if l.gap_ok == l.gap_total),
        'skus': sum(getattr(getattr(l, 'fact', None), 'sku_count', 0) or 0 for l in links),
    }
    group_owners = list(plan.group_owners.select_related('owner__profile'))
    tab_tasks = {
        key: [t for t in tasks if t.group in groups]
        for key, groups in TAB_GROUPS.items()
    }
    ctx = _common(
        request,
        plan=plan,
        tab=tab,
        tabs=TABS,
        tasks=tasks,
        ready=ready,
        tone=plan_tone,
        tone_label=svc.TONE_LABELS[plan_tone],
        risks=risks,
        open_risks=[r for r in risks if r.is_open],
        high_risks=high,
        links=links,
        product_summary=product_summary,
        timeline=_timeline(tasks),
        tab_tasks=tab_tasks,
        group_owners=group_owners,
        owner_rows=f.owner_choice_rows(dict(plan.group_owners.values_list('group', 'owner_id'))),
        go_conditions=go_rows,
        decisions=list(plan.decisions.select_related('decided_by__profile', 'condition_owner__profile')),
        reviews=reviews,
        logs=list(plan.logs.select_related('user__profile')[:200]),
        can_edit=can_edit,
        can_edit_header=perms.can_edit_header(plan, user),
        can_delete=perms.can_delete_plan(plan, user),
        is_approver=is_approver,
        is_coordinator=perms.is_coordinator(plan, user),
        task_add_form=f.TaskAddForm(initial={'owner': plan.coordinator_id, 'due_date': plan.launch_date}),
        task_form=f.TaskUpdateForm(),
        risk_form=f.RiskForm(initial={'owner': plan.coordinator_id}),
        plan_decision_form=f.PlanDecisionForm() if is_approver and plan.status == Status.PLAN_PENDING else None,
        go_form=f.GoDecisionForm() if is_approver and plan.status == Status.LAUNCH_PENDING else None,
        my_open=[t for t in tasks if t.mine and t.is_open],
        today=timezone.localdate(),
        back_url=reverse('ra_mat_sp:list'),
    )
    return render(request, 'ra_mat_sp/plan_detail.html', ctx)


def _redirect(plan, tab=''):
    url = plan.get_absolute_url()
    return redirect(f'{url}?tab={tab}' if tab else url)


def _form_error_text(form) -> str:
    for field, errors in form.errors.items():
        label = form.fields[field].label if field in form.fields else ''
        return f'{label}: {errors[0]}' if label else str(errors[0])
    return 'Dữ liệu không hợp lệ.'


def _run_action(request, plan: LaunchPlan, action: str) -> str:
    """Thực hiện thao tác; trả về tab cần quay lại. Lỗi nghiệp vụ → WorkflowError."""
    user = request.user
    post = request.POST
    can_edit = perms.can_edit_plan(plan, user)
    is_coord = can_edit and (perms.is_coordinator(plan, user) or perms.can_update(user))

    if action == 'submit_plan':
        if not is_coord:
            raise svc.WorkflowError('Chỉ người điều phối gửi duyệt kế hoạch.')
        svc.submit_plan(plan, user)
        messages.success(request, 'Đã gửi duyệt kế hoạch.')
        return 'overview'
    if action == 'decide_plan':
        if not perms.is_plan_approver(plan, user):
            raise svc.WorkflowError('Bạn không phải người duyệt kế hoạch này.')
        form = f.PlanDecisionForm(post)
        if not form.is_valid():
            raise svc.WorkflowError(_form_error_text(form))
        svc.decide_plan(plan, user, form.cleaned_data['decision'], form.cleaned_data['comment'])
        messages.success(request, 'Đã ghi quyết định duyệt kế hoạch.')
        return 'overview'
    if action == 'submit_go':
        if not is_coord:
            raise svc.WorkflowError('Chỉ người điều phối trình Go/No-Go.')
        svc.submit_go(plan, user)
        messages.success(request, 'Đã trình họp Go/No-Go.')
        return 'go'
    if action == 'decide_go':
        if not perms.is_plan_approver(plan, user):
            raise svc.WorkflowError('Bạn không phải người duyệt kế hoạch này.')
        form = f.GoDecisionForm(post)
        if not form.is_valid():
            raise svc.WorkflowError(_form_error_text(form))
        cd = form.cleaned_data
        svc.decide_go(plan, user, svc.GoInput(
            decision=cd['decision'], comment=cd['comment'], new_launch_date=cd['new_launch_date'],
            condition_text=cd['condition_text'], condition_owner=cd['condition_owner'],
            condition_due=cd['condition_due'],
        ))
        messages.success(request, 'Đã ghi quyết định Go/No-Go.')
        return 'go'
    if action == 'launch':
        if not is_coord:
            raise svc.WorkflowError('Chỉ người điều phối xác nhận ra mắt.')
        svc.mark_launched(plan, user)
        messages.success(request, 'Đã xác nhận ra mắt. Đánh giá D+1 / D+7 / D+30 mở theo ngày.')
        return 'post'
    if action in ('pause', 'resume', 'cancel'):
        decision = {'pause': Decision.PAUSED, 'resume': Decision.RESUMED, 'cancel': Decision.CANCELLED}[action]
        allowed = (is_coord or perms.is_plan_approver(plan, user)) if action != 'resume' else (
            perms.is_coordinator(plan, user) or perms.can_update(user) or perms.is_plan_approver(plan, user))
        if not allowed:
            raise svc.WorkflowError('Bạn không có quyền thao tác này.')
        svc.stop_plan(plan, user, decision, post.get('comment', ''))
        messages.success(request, f'Đã {Decision(decision).label.lower()} kế hoạch.')
        return 'overview'
    if action == 'task_update':
        task = get_object_or_404(LaunchTask, pk=post.get('task_id'), plan=plan)
        if not perms.can_update_task(plan, task, user):
            raise svc.WorkflowError('Bạn không cập nhật được công việc này.')
        form = f.TaskUpdateForm(post)
        if not form.is_valid():
            raise svc.WorkflowError(_form_error_text(form))
        cd = form.cleaned_data
        svc.update_task(
            task, user, status=cd['status'], evidence=cd['evidence'], delay_reason=cd['delay_reason'],
            owner=cd['owner'], due_date=cd['due_date'], can_assign=can_edit,
            start_date=cd['start_date'], collaborators=list(cd['collaborators']) if can_edit else None,
            files=request.FILES.getlist('files'),
        )
        messages.success(request, f'Đã cập nhật «{task.title}».')
        return post.get('return_tab') or 'timeline'
    if action == 'task_add':
        if not can_edit:
            raise svc.WorkflowError('Bạn không thêm được công việc.')
        form = f.TaskAddForm(post)
        if not form.is_valid():
            raise svc.WorkflowError(_form_error_text(form))
        cd = form.cleaned_data
        svc.add_task(
            plan, user, group=cd['group'], title=cd['title'], deliverable=cd['deliverable'], due_date=cd['due_date'],
            owner=cd['owner'], importance=cd['importance'], is_go_blocker=cd['is_go_blocker'],
            start_date=cd['start_date'], collaborators=list(cd['collaborators']),
        )
        messages.success(request, 'Đã thêm công việc.')
        return post.get('return_tab') or 'timeline'
    if action == 'task_delete':
        task = get_object_or_404(LaunchTask, pk=post.get('task_id'), plan=plan)
        if not can_edit:
            raise svc.WorkflowError('Bạn không xóa được công việc.')
        svc.delete_task(task, user)
        messages.success(request, 'Đã xóa công việc.')
        return post.get('return_tab') or 'timeline'
    if action == 'task_file_delete':
        task_file = get_object_or_404(LaunchTaskFile.objects.select_related('task'), pk=post.get('file_id'), task__plan=plan)
        if not perms.can_update_task(plan, task_file.task, user):
            raise svc.WorkflowError('Bạn không xóa được tệp này.')
        svc.delete_task_file(task_file, user)
        messages.success(request, 'Đã xóa tệp.')
        return post.get('return_tab') or 'timeline'
    if action == 'risk_add':
        if not (can_edit or plan.tasks.filter(owner=user).exists()) or plan.status in FINAL_STATUSES:
            raise svc.WorkflowError('Bạn không ghi nhận được rủi ro cho kế hoạch này.')
        form = f.RiskForm(post)
        if not form.is_valid():
            raise svc.WorkflowError(_form_error_text(form))
        svc.add_risk(plan, user, form.save(commit=False))
        messages.success(request, 'Đã ghi nhận rủi ro.')
        return 'overview'
    if action == 'risk_resolve':
        risk = get_object_or_404(LaunchRisk, pk=post.get('risk_id'), plan=plan)
        if not (can_edit or risk.owner_id == user.pk):
            raise svc.WorkflowError('Bạn không xử lý được rủi ro này.')
        svc.resolve_risk(risk, user, post.get('resolution', ''))
        messages.success(request, 'Đã đóng rủi ro.')
        return 'overview'
    if action == 'product_qty':
        if not can_edit:
            raise svc.WorkflowError('Bạn không sửa được sản lượng.')
        for link in plan.products.all():
            raw = (post.get(f'qty_{link.pk}') or '').strip()
            note = (post.get(f'note_{link.pk}') or '').strip()[:255]
            qty = int(raw) if raw.isdigit() else None
            if qty != link.planned_qty or note != link.note:
                link.planned_qty = qty
                link.note = note
                link.save(update_fields=['planned_qty', 'note'])
        svc.log(plan, user, 'products', 'Cập nhật sản lượng ra mắt theo sản phẩm.')
        messages.success(request, 'Đã lưu sản lượng ra mắt.')
        return 'products'
    if action == 'owners':
        if not can_edit:
            raise svc.WorkflowError('Bạn không đổi được người phụ trách nhóm.')
        svc.assign_group_owners(plan, user, svc.parse_owner_map(post))
        messages.success(request, 'Đã lưu người phụ trách từng nhóm.')
        return 'overview'
    if action == 'review':
        review = get_object_or_404(PostLaunchReview, pk=post.get('review_id'), plan=plan)
        if not can_edit:
            raise svc.WorkflowError('Chỉ người điều phối ghi đánh giá sau ra mắt.')
        form = f.ReviewForm(post, instance=review, prefix=f'rv{review.pk}')
        if not form.is_valid():
            raise svc.WorkflowError(_form_error_text(form))
        cleaned = {k: form.cleaned_data[k] for k in form.Meta.fields}
        review.refresh_from_db()
        svc.submit_review(review, user, cleaned)
        messages.success(request, f'Đã lưu đánh giá {review.get_milestone_display()}.')
        return 'post'
    raise svc.WorkflowError('Thao tác không hợp lệ.')


@login_required
@require_POST
def plan_action(request, pk, action):
    plan = get_object_or_404(_plan_qs(), pk=pk)
    if not perms.can_view_plan(plan, request.user):
        return _deny(request, perms.MENU_PLANS)
    tab = request.POST.get('return_tab') or ''
    try:
        with transaction.atomic():
            tab = _run_action(request, plan, action)
    except svc.WorkflowError as exc:
        messages.error(request, str(exc))
    invalidate_plan_badges(plan)
    if request.POST.get('next') == 'my_tasks':
        return redirect('ra_mat_sp:my_tasks')
    return _redirect(plan, tab)


# ---------------------------------------------------------------------------
# Việc của tôi, chờ duyệt
# ---------------------------------------------------------------------------

@login_required
def my_tasks(request):
    user = request.user
    today = timezone.localdate()
    show = request.GET.get('show') or 'open'
    qs = LaunchTask.objects.filter(owner=user).exclude(plan__status__in=FINAL_STATUSES + (Status.PAUSED,))
    if show == 'open':
        qs = qs.filter(status__in=OPEN_TASK_STATUSES)
    tasks = list(qs.select_related('plan', 'owner__profile').prefetch_related(
        'collaborators__profile', 'files').order_by('due_date', 'pk'))
    for t in tasks:
        t.can_update = perms.can_update_task(t.plan, t, user)
    soon_end = today + timedelta(days=7)
    # Việc chờ tôi xác nhận: việc của người khác đang vướng mắc, thuộc kế hoạch tôi điều phối
    # hoặc nhóm tôi chịu trách nhiệm chính.
    owned_groups = Q()
    for plan_id, group in LaunchPlanGroupOwner.objects.filter(owner=user).values_list('plan_id', 'group'):
        owned_groups |= Q(plan_id=plan_id, group=group)
    confirm_filter = Q(plan__coordinator=user)
    if owned_groups:
        confirm_filter |= owned_groups
    confirm = list(
        LaunchTask.objects.filter(confirm_filter, status=TaskStatus.BLOCKED)
        .exclude(owner=user)
        .exclude(plan__status__in=FINAL_STATUSES + (Status.PAUSED,))
        .select_related('plan', 'owner__profile').prefetch_related('collaborators__profile', 'files')
        .order_by('due_date', 'pk')
    )
    for t in confirm:
        t.can_update = perms.can_update_task(t.plan, t, user)
    collab = list(
        LaunchTask.objects.filter(collaborators=user, status__in=OPEN_TASK_STATUSES)
        .exclude(owner=user)
        .exclude(plan__status__in=FINAL_STATUSES + (Status.PAUSED,))
        .select_related('plan', 'owner__profile').prefetch_related('collaborators__profile', 'files')
        .order_by('due_date', 'pk')
    )
    for t in collab:
        t.can_update = False
    buckets = {
        'collab': collab,
        'overdue': [t for t in tasks if t.is_overdue],
        'soon': [t for t in tasks if t.is_open and not t.is_overdue and t.due_date <= soon_end],
        'confirm': confirm,
        'open': [t for t in tasks if t.is_open and not t.is_overdue and t.due_date > soon_end],
    }
    risks = list(
        LaunchRisk.objects.filter(owner=user, state=LaunchRisk.STATE_OPEN).exclude(plan__status__in=FINAL_STATUSES)
        .select_related('plan')
    )
    return render(request, 'ra_mat_sp/my_tasks.html', _common(
        request, tasks=tasks, buckets=buckets, risks=risks, show=show, today=today, task_form=f.TaskUpdateForm(),
        overdue=len(buckets['overdue']), rm_active='my_tasks',
    ))


@login_required
def task_file(request, pk):
    import mimetypes
    import os
    from urllib.parse import quote

    from django.http import FileResponse, Http404, HttpResponseForbidden

    row = get_object_or_404(LaunchTaskFile.objects.select_related('task__plan'), pk=pk)
    if not perms.can_view_plan(row.task.plan, request.user):
        return HttpResponseForbidden('Không có quyền xem tệp.')
    try:
        handle = row.file.open('rb')
    except (FileNotFoundError, OSError):
        raise Http404('Không tìm thấy tệp.')
    name = row.display_name
    content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    inline = request.GET.get('download') != '1' and (
        content_type.startswith('image/') or content_type == 'application/pdf')
    response = FileResponse(handle, content_type=content_type)
    response['Content-Disposition'] = f"{'inline' if inline else 'attachment'}; filename*=UTF-8''{quote(name)}"
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@login_required
def approve_queue(request):
    user = request.user
    plans = list(_plan_qs().filter(approver=user, status__in=APPROVAL_STATUSES).order_by('launch_date'))
    plans = _decorate(plans)
    return render(request, 'ra_mat_sp/approve_queue.html', _common(
        request, plans=plans, can_approve=perms.has_approve_permission(user), rm_active='approve',
    ))


# ---------------------------------------------------------------------------
# Thiết lập checklist mẫu
# ---------------------------------------------------------------------------

@login_required
def module_settings(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_SETTINGS):
        return _deny(request, perms.MENU_SETTINGS)
    can_edit = perms.can_manage_settings(user)
    edit_item = None
    edit_id = request.GET.get('sua') or request.POST.get('item_id')
    if edit_id and str(edit_id).isdigit():
        edit_item = ChecklistTemplateItem.objects.filter(pk=int(edit_id)).first()
    form = f.TemplateItemForm(instance=edit_item)
    if request.method == 'POST':
        if not can_edit:
            return _deny(request, perms.MENU_SETTINGS)
        op = request.POST.get('op')
        if op == 'restore':
            n = load_default_checklist(ChecklistTemplateItem)
            added = svc.sync_checklist_to_open_plans()
            messages.success(
                request,
                f'Đã nạp lại checklist mặc định ({n} dòng mới) và bổ sung {added} việc vào kế hoạch đang mở.',
            )
            return redirect('ra_mat_sp:settings')
        if op == 'owners':
            try:
                svc.save_group_defaults(svc.parse_owner_map(request.POST))
            except svc.WorkflowError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, 'Đã lưu người phụ trách mặc định từng nhóm.')
            return redirect('ra_mat_sp:settings')
        if op == 'toggle' and edit_item:
            edit_item.is_active = not edit_item.is_active
            edit_item.save(update_fields=['is_active'])
            messages.success(request, 'Đã cập nhật trạng thái dòng checklist.')
            return redirect('ra_mat_sp:settings')
        form = f.TemplateItemForm(request.POST, instance=edit_item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã lưu dòng checklist mẫu. Kế hoạch đang mở sẽ nhận việc mới khi nạp mặc định.')
            return redirect('ra_mat_sp:settings')
    items = list(ChecklistTemplateItem.objects.all())
    labels = catalog.group_labels()
    milestones: OrderedDict[int, list] = OrderedDict()
    for item in items:
        item.group_label = labels.get(item.product_group, item.product_group) if item.product_group else ''
        milestones.setdefault(item.offset_days, []).append(item)
    selected = dict(LaunchGroupDefault.objects.values_list('group', 'owner_id'))
    return render(request, 'ra_mat_sp/settings.html', _common(
        request, form=form, edit_item=edit_item, can_edit=can_edit, rm_active='settings',
        milestones=[(milestone_label(k), v) for k, v in milestones.items()],
        weights=[(TaskGroup(k).label, w) for k, w in GROUP_WEIGHTS.items()],
        owner_rows=f.owner_choice_rows(selected),
    ))
