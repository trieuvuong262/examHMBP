from __future__ import annotations

import json
import mimetypes
import os
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Value, When
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from hrm.menu_permissions import handle_menu_access_denied, user_can_access_resolved_menu
from hrm.module_permissions import MODULE_THIET_KE_SP
from san_xuat.design_nas_storage import design_file_abs_path
from san_xuat.list_grid import apply_sx_list_sort, sx_list_grid_context
from utilities.date_range_filter import date_range_from_span, date_range_span_context, parse_date_range_span

from . import forms as f
from . import permissions as perms
from . import presenters
from .list_grid import LIST_KEY
from .models import (
    DESIGN_KINDS,
    DONE_STATUSES,
    DOSSIER_KINDS,
    FINAL_STATUSES,
    IN_PROGRESS_STATUSES,
    SAMPLE_KINDS,
    STOPPED_STATUSES,
    ApprovalCondition,
    ApprovalDecision,
    ApprovalStage,
    Attachment,
    AttachmentKind,
    Colorway,
    Criterion,
    DesignVersion,
    DossierMember,
    EvaluationItem,
    HandoverReceipt,
    MemberGroup,
    Notification,
    Priority,
    ProductDevelopment,
    ProductGroup,
    Role,
    SampleEvaluation,
    SampleVersion,
    Status,
    Task,
    TechnicalPack,
)
from .services import notify as nt
from .services import reports, sla
from .services import workflow as wf

M = MODULE_THIET_KE_SP

TABS = (
    ('overview', 'Tổng quan', 'bi-info-circle'),
    ('design', 'Thiết kế & phiên bản', 'bi-palette'),
    ('technical', 'Kỹ thuật / BOM', 'bi-rulers'),
    ('sample', 'Mẫu & đánh giá', 'bi-scissors'),
    ('costing', 'Giá thành', 'bi-cash-coin'),
    ('approval', 'Phê duyệt', 'bi-check2-circle'),
    ('files', 'Trao đổi & tệp', 'bi-chat-dots'),
    ('history', 'Lịch sử', 'bi-clock-history'),
)
TAB_KEYS = {t[0] for t in TABS}

QUICK_FILTERS = (
    ('', 'Tất cả'),
    ('in_progress', 'Đang phát triển'),
    ('waiting_approval', 'Chờ duyệt'),
    ('mine', 'Chờ tôi xử lý'),
    ('overdue', 'Quá hạn'),
    ('done', 'Đã bàn giao / đóng'),
    ('stopped', 'Tạm dừng / hủy'),
)


def _deny(request, menu: str):
    return handle_menu_access_denied(request, M, menu)


def _dossier_qs():
    return ProductDevelopment.objects.select_related(
        'proposer__profile', 'owner__profile', 'approver__profile', 'designer__profile',
        'technician__profile', 'sample_maker__profile', 'qa_user__profile', 'costing_user__profile',
        'approved_design_version', 'final_sample_version',
    )


def _get_dossier(pk):
    return get_object_or_404(_dossier_qs(), pk=pk)


def _redirect_tab(dossier, tab: str = ''):
    url = dossier.get_absolute_url()
    return redirect(f'{url}?tab={tab}' if tab else url)


def _common(request, **extra):
    user = request.user
    ctx = {
        'tksp_can_create': perms.can_create(user),
        'tksp_can_settings': perms.can_manage_settings(user),
        'tksp_can_approve_menu': user_can_access_resolved_menu(user, M, perms.MENU_APPROVE),
    }
    ctx.update(extra)
    return ctx


# ---------------------------------------------------------------------------
# Danh sách
# ---------------------------------------------------------------------------

def _annotated_list_qs():
    open_main = Task.objects.filter(
        dossier=OuterRef('pk'), state=Task.STATE_OPEN, is_main=True,
        receipt__isnull=True, condition__isnull=True,
    ).order_by('due_at', 'pk')
    return _dossier_qs().annotate(
        step_due_at=Subquery(open_main.values('due_at')[:1]),
        step_assignee_id=Subquery(open_main.values('assignee_id')[:1]),
        step_assignee_name=Subquery(open_main.values('assignee__profile__full_name')[:1]),
        priority_rank=Case(
            When(priority=Priority.URGENT, then=Value(0)),
            When(priority=Priority.HIGH, then=Value(1)),
            When(priority=Priority.NORMAL, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        ),
    )


def _apply_quick(qs, quick: str, user):
    now = timezone.now()
    if quick == 'in_progress':
        return qs.filter(status__in=IN_PROGRESS_STATUSES)
    if quick == 'waiting_approval':
        return qs.filter(status__in=presenters.APPROVAL_STATUSES)
    if quick == 'mine':
        return qs.filter(tasks__assignee=user, tasks__state=Task.STATE_OPEN).exclude(
            status__in=STOPPED_STATUSES,
        ).distinct()
    if quick == 'overdue':
        return qs.filter(tasks__state=Task.STATE_OPEN, tasks__due_at__lt=now).exclude(
            status__in=(*STOPPED_STATUSES, Status.CLOSED),
        ).distinct()
    if quick == 'done':
        return qs.filter(status__in=DONE_STATUSES)
    if quick == 'stopped':
        return qs.filter(status__in=STOPPED_STATUSES)
    return qs


@login_required
def dossier_list(request):
    user = request.user
    member_only = not perms.can_view_module(user)
    if member_only and not perms.has_memberships(user):
        return _deny(request, perms.MENU_DOSSIERS)
    g = request.GET
    q = (g.get('q') or '').strip()
    statuses = [s for s in g.getlist('status') if s in Status.values]
    quick = (g.get('quick') or '').strip()
    group = (g.get('group') or '').strip()
    owner_id = (g.get('owner') or '').strip()
    approver_id = (g.get('approver') or '').strip()
    collection = (g.get('collection') or '').strip()

    qs = _annotated_list_qs()
    if member_only:
        qs = qs.filter(members__user=user)
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(official_product_code__icontains=q))
    if statuses:
        qs = qs.filter(status__in=statuses)
    if group in ProductGroup.values:
        qs = qs.filter(product_group=group)
    if collection:
        qs = qs.filter(collection=collection)
    if owner_id.isdigit():
        qs = qs.filter(owner_id=int(owner_id))
    if approver_id.isdigit():
        qs = qs.filter(approver_id=int(approver_id))
    qs = _apply_quick(qs, quick, user)
    date_kind, date_from, date_to = _list_date_range(g)
    if date_from or date_to:
        field = LIST_DATE_FIELDS[date_kind][1]
        if date_from:
            qs = qs.filter(**{f'{field}__gte': date_from})
        if date_to:
            qs = qs.filter(**{f'{field}__lte': date_to})
    qs = apply_sx_list_sort(qs, request, LIST_KEY)

    page = Paginator(qs, 30).get_page(g.get('page'))
    rows = _decorate_rows(list(page.object_list))

    params = g.copy()
    params.pop('page', None)
    has_filters = any([q, statuses, quick, group, owner_id, approver_id, collection, date_from, date_to])
    ctx = _common(
        request,
        page_obj=page,
        dossiers=rows,
        total_count=page.paginator.count,
        query_string=params.urlencode(),
        filter_q=q, filter_status=statuses[0] if len(statuses) == 1 else '', filter_statuses=statuses,
        filter_quick=quick, filter_group=group,
        filter_owner=owner_id, filter_approver=approver_id, filter_collection=collection,
        has_filters=has_filters,
        status_choices=Status.choices,
        group_choices=ProductGroup.choices,
        collection_choices=_collection_choices(),
        quick_filters=QUICK_FILTERS,
        owner_choices=_people_with('tksp_owned'),
        approver_choices=_people_with('tksp_approving'),
        date_kind_choices=[(k, label) for k, (label, _f) in LIST_DATE_FIELDS.items()],
        filter_date_kind=date_kind, date_from=date_from, date_to=date_to,
        range_all=not (date_from or date_to),
        **date_range_span_context(date_from, date_to),
        **sx_list_grid_context(request, LIST_KEY),
    )
    return render(request, 'thiet_ke_sp/dossier_list.html', ctx)


LIST_DATE_FIELDS = {
    'proposed': ('Ngày đề xuất', 'proposed_date'),
    'launch': ('Ngày ra mắt', 'launch_date'),
    'step_due': ('Hạn bước hiện tại', 'step_due_at__date'),
}


def _parse_ymd(raw):
    try:
        return date.fromisoformat((raw or '').strip())
    except ValueError:
        return None


def _list_date_range(g):
    """Không chọn ngày = không lọc (xem tất cả)."""
    kind = g.get('date_kind') if g.get('date_kind') in LIST_DATE_FIELDS else 'proposed'
    span = (g.get('span') or '').strip()
    if span == 'all':
        return kind, None, None
    date_from, date_to = _parse_ymd(g.get('from')), _parse_ymd(g.get('to'))
    if span.isdigit() and not (date_from or date_to):
        date_to = timezone.localdate()
        date_from = date_range_from_span(date_to, parse_date_range_span(span))
    if date_from and date_to and date_from > date_to:
        date_from, date_to = date_to, date_from
    return kind, date_from, date_to


def _decorate_rows(rows: list) -> list:
    covers = presenters.cover_map(d.pk for d in rows)
    now = timezone.now()
    for d in rows:
        d.cover = covers.get(d.pk)
        d.step_late_days = 0
        if d.step_due_at and d.step_due_at < now and d.status not in (*STOPPED_STATUSES, Status.CLOSED):
            d.step_late_days = max((timezone.localdate() - timezone.localtime(d.step_due_at).date()).days, 1)
    return rows


def _collection_choices() -> list[str]:
    return list(
        ProductDevelopment.objects.exclude(collection='').order_by('collection')
        .values_list('collection', flat=True).distinct()
    )


def _people_with(related: str):
    return list(
        f.active_users().filter(**{f'{related}__isnull': False}).distinct()
    )


# ---------------------------------------------------------------------------
# Tạo / sửa đề bài
# ---------------------------------------------------------------------------

def _brief_fields(form) -> dict:
    return {name: form.cleaned_data.get(name) for name in form.Meta.fields}


@login_required
def dossier_create(request):
    user = request.user
    if not perms.can_create(user):
        return _deny(request, perms.MENU_DOSSIERS)
    form = f.DossierForm(request.POST or None, user=user)
    if request.method == 'POST' and form.is_valid():
        submit = request.POST.get('submit_action') == 'submit'
        try:
            dossier = wf.create_dossier(user, fields=_brief_fields(form), submit=False)
        except wf.WorkflowError as exc:
            messages.error(request, str(exc))
        else:
            for upload in request.FILES.getlist('reference_files'):
                try:
                    wf.upload_attachment(dossier, user, uploaded_file=upload, kind=AttachmentKind.REFERENCE)
                except wf.WorkflowError as exc:
                    messages.warning(request, f'{upload.name}: {exc}')
            if submit:
                try:
                    wf.submit_brief(dossier, user, due_at=f.parse_due(request.POST.get('due_at')))
                    messages.success(request, f'Đã tạo {dossier.code} và gửi duyệt đề bài.')
                except wf.WorkflowError as exc:
                    messages.warning(request, f'Đã lưu nháp {dossier.code}. Chưa gửi duyệt: {exc}')
            else:
                messages.success(request, f'Đã lưu nháp {dossier.code}.')
            return redirect(dossier.get_absolute_url())
    return render(request, 'thiet_ke_sp/dossier_form.html', _common(
        request, form=form, dossier=None, default_due=sla.due_at_for(Status.BRIEF_PENDING),
    ))


@login_required
def dossier_edit(request, pk):
    user = request.user
    dossier = _get_dossier(pk)
    if not perms.can_edit_brief(dossier, user):
        messages.error(request, 'Chỉ sửa đề bài khi hồ sơ còn nháp hoặc đang được yêu cầu bổ sung.')
        return redirect(dossier.get_absolute_url())
    form = f.DossierForm(request.POST or None, instance=dossier, user=user)
    if request.method == 'POST' and form.is_valid():
        fields = _brief_fields(form)
        dossier.refresh_from_db()
        try:
            wf.update_brief(dossier, user, fields=fields)
            for upload in request.FILES.getlist('reference_files'):
                wf.upload_attachment(dossier, user, uploaded_file=upload, kind=AttachmentKind.REFERENCE)
            if request.POST.get('submit_action') == 'submit':
                wf.submit_brief(dossier, user, due_at=f.parse_due(request.POST.get('due_at')))
                messages.success(request, 'Đã gửi duyệt đề bài.')
            else:
                messages.success(request, 'Đã lưu đề bài.')
        except wf.WorkflowError as exc:
            messages.error(request, str(exc))
        return redirect(dossier.get_absolute_url())
    return render(request, 'thiet_ke_sp/dossier_form.html', _common(
        request, form=form, dossier=dossier, default_due=sla.due_at_for(Status.BRIEF_PENDING),
        references=dossier.attachments.filter(kind=AttachmentKind.REFERENCE, is_deleted=False),
    ))


@login_required
@require_POST
def dossier_delete(request, pk):
    dossier = _get_dossier(pk)
    code = dossier.code
    try:
        wf.delete_draft(dossier, request.user)
    except wf.WorkflowError as exc:
        messages.error(request, str(exc))
        return redirect(dossier.get_absolute_url())
    messages.success(request, f'Đã xóa hồ sơ nháp {code}.')
    return redirect('thiet_ke_sp:list')


# ---------------------------------------------------------------------------
# Chi tiết
# ---------------------------------------------------------------------------

def _live_atts(qs):
    return [a for a in qs if not a.is_deleted]


@login_required
def dossier_detail(request, pk):
    user = request.user
    dossier = _get_dossier(pk)
    if not perms.can_view_dossier(dossier, user):
        return _deny(request, perms.MENU_DOSSIERS)
    tab = request.GET.get('tab') or 'overview'
    if tab not in TAB_KEYS:
        tab = 'overview'

    att_qs = Attachment.objects.select_related('uploaded_by__profile', 'colorway').order_by('kind', '-uploaded_at')
    design_versions = list(
        dossier.design_versions.select_related('created_by__profile', 'updated_by__profile').prefetch_related(
            Prefetch('colorways', queryset=Colorway.objects.order_by('sort_order', 'pk')),
            Prefetch('attachments', queryset=att_qs),
            'comments__author__profile',
        )
    )
    samples = list(
        dossier.sample_versions.select_related('design_version', 'maker__profile', 'tech_pack').prefetch_related(
            Prefetch('attachments', queryset=att_qs),
            'tech_pack__material_lines',
            Prefetch('evaluations__items', queryset=EvaluationItem.objects.order_by('pk')),
            'evaluations__evaluator__profile',
            'evaluations__fix_owner__profile',
            'evaluations__fix_done_by__profile',
        )
    )
    today = timezone.localdate()
    can_close_fix = dossier.status not in FINAL_STATUSES
    for dv in design_versions:
        live = _live_atts(dv.attachments.all())
        dv.live_atts = live
        dv.current_atts = {a.kind: a for a in live if a.is_current and a.kind in (
            AttachmentKind.FRONT, AttachmentKind.BACK, AttachmentKind.DESIGN_SOURCE, AttachmentKind.DESIGN_PREVIEW)}
        dv.detail_atts = [a for a in live if a.kind == AttachmentKind.DETAIL]
        dv.archived_atts = [a for a in live if not a.is_current]
        cw_images = {}
        for a in live:
            if a.kind == AttachmentKind.COLORWAY and a.colorway_id:
                cw_images.setdefault(a.colorway_id, []).append(a)
        dv.colorway_rows = [(cw, cw_images.get(cw.pk, [])) for cw in dv.colorways.all()]
    for sv in samples:
        live = _live_atts(sv.attachments.all())
        sv.photos = [a for a in live if a.kind == AttachmentKind.SAMPLE_PHOTO]
        sv.tech_files = [a for a in live if a.kind == AttachmentKind.TECH_SPEC]
        sv.eval_files = [a for a in live if a.kind == AttachmentKind.EVALUATION]
        pack = getattr(sv, 'tech_pack', None)
        sv.pack = pack
        sv.lines = list(pack.material_lines.all()) if pack else []
        for ev in sv.evaluations.all():
            ev.can_fix = can_close_fix and ev.needs_fix and ev.fix_owner_id == user.pk
            ev.fix_late = ev.needs_fix and ev.fix_due is not None and ev.fix_due < today

    current_dvs = sorted((dv for dv in design_versions if dv.is_current), key=lambda dv: dv.option_no)
    current_dv = current_dvs[0] if current_dvs else None
    current_sv = next((sv for sv in samples if sv.is_current), None)
    flags = presenters.action_flags(dossier, user)
    multi_options = len(current_dvs) > 1
    for dv in current_dvs:
        dv.can_edit = flags['edit_design'] and dv.is_editable
        dv.form = f.DesignVersionForm(instance=dv, auto_id=f'id_dv{dv.pk}_%s') if dv.can_edit else None
        dv.can_upload = wf.can_upload(dossier, user, AttachmentKind.FRONT, design_version=dv)
        dv.needs_note = dv.can_edit and wf.needs_change_note(dv)
    submitted_dvs = [dv for dv in current_dvs if dv.state == DesignVersion.STATE_SUBMITTED]
    checklist_title, checklist = presenters.step_checklist(dossier)
    main_task = wf.current_main_task(dossier)
    open_tasks = list(
        dossier.tasks.filter(state=Task.STATE_OPEN).select_related('assignee__profile', 'receipt', 'condition')
    )
    for t in open_tasks:
        t.mine = t.assignee_id == user.pk
    setting = sla.get_settings()
    status_due_default = sla.due_at_for(_next_due_step(dossier.status), setting=setting)
    sla_due = {s: sla.due_at_for(s, setting=setting) for s in Status.values}

    level_files = list(
        dossier.attachments.filter(design_version__isnull=True, sample_version__isnull=True, is_deleted=False)
        .select_related('uploaded_by__profile').order_by('kind', '-uploaded_at')
    )
    dossier_files = [a for a in level_files if a.kind != AttachmentKind.PRODUCT_PHOTO]
    product_photos = sorted((a for a in level_files if a.kind == AttachmentKind.PRODUCT_PHOTO),
                            key=lambda a: a.uploaded_at, reverse=True)
    for a in product_photos:
        a.can_delete = a.uploaded_by_id == user.pk or perms.has_role(dossier, user, Role.OWNER)
    members = list(dossier.members.select_related('user__profile', 'added_by__profile'))
    handover = getattr(dossier, 'handover', None) if dossier.status in (Status.HANDED_OVER, Status.CLOSED) else None
    receipts = list(handover.receipts.select_related('receiver__profile', 'confirmed_by__profile')) if handover else []
    for r in receipts:
        r.can_confirm = not r.is_confirmed and dossier.status == Status.HANDED_OVER and r.receiver_id == user.pk
    conditions = list(dossier.conditions.select_related('assignee__profile', 'done_by__profile'))
    for c in conditions:
        c.can_complete = not c.is_done and dossier.status == Status.APPROVED and (
            c.assignee_id == user.pk or perms.is_dossier_approver(dossier, user))

    eval_roles = wf.evaluator_roles_for(dossier, user) if flags['evaluate'] else []
    ctx = _common(
        request,
        dossier=dossier,
        tab=tab,
        tabs=TABS,
        steps=presenters.stepper(dossier),
        roles_rail=presenters.roles_rail(dossier),
        checklist_title=checklist_title,
        checklist=checklist,
        checklist_ok=all(ok for _l, ok in checklist) if checklist else False,
        main_task=main_task,
        open_tasks=open_tasks,
        flags=flags,
        cover=presenters.cover_map([dossier.pk]).get(dossier.pk),
        design_versions=design_versions,
        current_dv=current_dv,
        current_dvs=current_dvs,
        multi_options=multi_options,
        has_options=any(dv.option_no > 1 for dv in design_versions),
        submitted_dvs=submitted_dvs,
        design_scope=wf.design_scope_label(dossier) if current_dvs else '',
        design_modal_size='modal-lg' if len(submitted_dvs) > 1 else '',
        samples=samples,
        current_sv=current_sv,
        approvals=list(dossier.approvals.select_related(
            'decided_by__profile', 'design_version', 'sample_version').prefetch_related('conditions')),
        conditions=conditions,
        comments=list(dossier.comments.select_related('author__profile', 'design_version', 'sample_version')),
        dossier_files=dossier_files,
        product_photos=product_photos,
        can_upload_product_photo=wf.can_upload(dossier, user, AttachmentKind.PRODUCT_PHOTO),
        members=members,
        member_groups=MemberGroup.choices,
        member_users=list(f.active_users()) if flags['edit_roles'] else [],
        audit_logs=list(dossier.audit_logs.select_related('actor__profile')[:300]),
        handover=handover,
        receipts=receipts,
        due_default=status_due_default,
        sla_due=sla_due,
        design_kinds=[(k, AttachmentKind(k).label) for k in DESIGN_KINDS if k != AttachmentKind.COLORWAY],
        sample_kinds=[(k, AttachmentKind(k).label) for k in SAMPLE_KINDS if k != AttachmentKind.EVALUATION],
        dossier_kinds=[(k, AttachmentKind(k).label) for k in DOSSIER_KINDS],
        criteria=Criterion.choices,
        colorway_form=f.ColorwayForm() if flags['edit_design'] else None,
        sample_form=f.SampleForm(instance=current_sv) if flags['edit_sample'] and current_sv else None,
        tech_pack_form=(
            f.TechPackForm(instance=current_sv.pack or TechnicalPack(sample_version=current_sv))
            if flags['edit_tech_pack'] and current_sv else None
        ),
        evaluation_form=f.EvaluationForm(allowed_roles=eval_roles) if eval_roles else None,
        costing_form=f.CostingForm(instance=dossier) if flags['edit_costing'] else None,
        roles_form=f.RolesForm(dossier=dossier) if flags['edit_roles'] else None,
        handover_form=f.HandoverForm() if flags['handover'] else None,
        condition_users=list(f.active_users()) if flags['decide_master'] else [],
        can_upload_dossier_other=wf.can_upload(dossier, user, AttachmentKind.OTHER),
        can_upload_reference=wf.can_upload(dossier, user, AttachmentKind.REFERENCE),
        can_upload_cost=wf.can_upload(dossier, user, AttachmentKind.COST),
        can_upload_sample=bool(current_sv) and wf.can_upload(dossier, user, AttachmentKind.SAMPLE_PHOTO, sample_version=current_sv),
        can_upload_tech=bool(current_sv) and wf.can_upload(dossier, user, AttachmentKind.TECH_SPEC, sample_version=current_sv),
        can_upload_eval=bool(current_sv) and wf.can_upload(dossier, user, AttachmentKind.EVALUATION, sample_version=current_sv),
        material_total=sum((ln.line_cost or 0) for ln in (current_sv.lines if current_sv else [])),
        user_is_participant=perms.is_participant(dossier, user),
        costing=presenters.costing_summary(dossier),
        due_pct=presenters.due_progress(dossier, main_task),
        age_days=presenters.dossier_age_days(dossier),
    )
    return render(request, 'thiet_ke_sp/dossier_detail.html', ctx)


_NEXT_STEP = {
    Status.DRAFT: Status.BRIEF_PENDING,
    Status.BRIEF_NEEDS_INFO: Status.BRIEF_PENDING,
    Status.BRIEF_PENDING: Status.DESIGNING,
    Status.DESIGNING: Status.DESIGN_PENDING,
    Status.DESIGN_REVISE: Status.DESIGN_PENDING,
    Status.DESIGN_PENDING: Status.SAMPLING,
    Status.SAMPLING: Status.SAMPLE_EVAL_PENDING,
    Status.SAMPLE_REVISE: Status.SAMPLE_EVAL_PENDING,
    Status.SAMPLE_EVAL_PENDING: Status.MASTER_PENDING,
    Status.MASTER_PENDING: Status.APPROVED,
    Status.APPROVED: Status.HANDED_OVER,
}


def _next_due_step(status: str) -> str:
    return _NEXT_STEP.get(status, Status.HANDED_OVER)


# ---------------------------------------------------------------------------
# Thao tác (POST)
# ---------------------------------------------------------------------------

def _form_error_text(form) -> str:
    parts = []
    for name, errors in form.errors.items():
        label = form.fields[name].label if name in form.fields else ''
        parts.append(f'{label}: {"; ".join(errors)}' if label else '; '.join(errors))
    return ' · '.join(parts) or 'Dữ liệu không hợp lệ.'


def _decimal_or_none(raw):
    raw = (raw or '').strip().replace(',', '.')
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        raise wf.WorkflowError(f'Số không hợp lệ: {raw}')
    if value < 0:
        raise wf.WorkflowError('Không nhập số âm.')
    return value


def _material_lines(post) -> list[dict]:
    names = post.getlist('line_name')
    specs = post.getlist('line_spec')
    consumptions = post.getlist('line_consumption')
    units = post.getlist('line_unit')
    prices = post.getlist('line_price')
    mains = post.getlist('line_main')
    lines = []
    for i, name in enumerate(names):
        name = (name or '').strip()
        if not name:
            continue
        lines.append({
            'material_name': name[:200],
            'spec': (specs[i] if i < len(specs) else '').strip()[:255],
            'consumption': _decimal_or_none(consumptions[i] if i < len(consumptions) else ''),
            'unit': (units[i] if i < len(units) else '').strip()[:30],
            'unit_price': _decimal_or_none(prices[i] if i < len(prices) else ''),
            'is_main': (mains[i] if i < len(mains) else '1') == '1',
        })
    return lines


def _conditions(post) -> list[wf.ConditionInput]:
    contents = post.getlist('cond_content')
    assignees = post.getlist('cond_assignee')
    dues = post.getlist('cond_due')
    users = {u.pk: u for u in f.active_users().filter(pk__in=[a for a in assignees if a.isdigit()])}
    rows = []
    for i, content in enumerate(contents):
        content = (content or '').strip()
        if not content:
            continue
        assignee_id = assignees[i] if i < len(assignees) else ''
        rows.append(wf.ConditionInput(
            content=content[:500],
            assignee=users.get(int(assignee_id)) if assignee_id.isdigit() else None,
            due_at=f.parse_due(dues[i] if i < len(dues) else ''),
        ))
    return rows


def _task_of(dossier, post) -> Task:
    return get_object_or_404(Task, pk=post.get('task_id'), dossier=dossier)


def _run_action(request, dossier: ProductDevelopment, action: str) -> tuple[str, str]:
    """Trả về (tab quay lại, thông báo thành công)."""
    user = request.user
    post = request.POST
    due = f.parse_due(post.get('due_at'))
    comment = (post.get('comment') or '').strip()

    if action == 'submit_brief':
        wf.submit_brief(dossier, user, due_at=due)
        return 'overview', 'Đã gửi duyệt đề bài.'
    if action == 'brief_decide':
        wf.decide_brief(dossier, user, decision=post.get('decision', ''), comment=comment, due_at=due)
        return 'approval', 'Đã ghi nhận quyết định duyệt đề bài.'

    if action == 'design_save':
        dv = get_object_or_404(DesignVersion, pk=post.get('design_version_id'), dossier=dossier)
        form = f.DesignVersionForm(post, instance=DesignVersion.objects.get(pk=dv.pk))
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        wf.save_design_version(dv, user, fields={k: form.cleaned_data[k] for k in form.Meta.fields})
        return 'design', f'Đã lưu nội dung thiết kế {dv.label}.'
    if action == 'colorway_add':
        dv = get_object_or_404(DesignVersion, pk=post.get('design_version_id'), dossier=dossier)
        form = f.ColorwayForm(post)
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        cw = wf.add_colorway(dv, user, **form.cleaned_data)
        upload = request.FILES.get('colorway_file')
        if upload:
            wf.upload_attachment(dossier, user, uploaded_file=upload, kind=AttachmentKind.COLORWAY,
                                 design_version=dv, colorway=cw)
        return 'design', f'Đã thêm colorway «{cw.name}».'
    if action == 'colorway_delete':
        cw = get_object_or_404(Colorway, pk=post.get('colorway_id'), design_version__dossier=dossier)
        wf.delete_colorway(cw, user)
        return 'design', 'Đã xóa colorway.'
    if action == 'design_option_add':
        source = None
        if (post.get('copy_from') or '').isdigit():
            source = get_object_or_404(DesignVersion, pk=post['copy_from'], dossier=dossier, is_current=True)
        dv = wf.add_design_option(dossier, user, copy_from=source)
        return 'design', f'Đã thêm {dv.option_label}.'
    if action == 'design_option_drop':
        dv = get_object_or_404(DesignVersion, pk=post.get('design_version_id'), dossier=dossier)
        wf.drop_design_option(dv, user)
        return 'design', f'Đã bỏ {dv.option_label}.'
    if action == 'design_submit':
        wf.submit_design(dossier, user, due_at=due)
        return 'design', 'Đã gửi duyệt thiết kế.'
    if action == 'design_decide':
        wf.decide_design(dossier, user, decision=post.get('decision', ''), comment=comment, due_at=due,
                         option_id=post.get('option_id'), keep_ids=post.getlist('keep_ids'))
        return 'design', 'Đã ghi nhận quyết định duyệt thiết kế.'
    if action == 'design_change':
        wf.request_design_change_from_sample(dossier, user, comment=comment, due_at=due)
        return 'design', 'Đã yêu cầu chỉnh thiết kế — mở phiên bản thiết kế mới.'

    if action == 'sample_save':
        sv = get_object_or_404(SampleVersion, pk=post.get('sample_version_id'), dossier=dossier)
        form = f.SampleForm(post, instance=SampleVersion.objects.get(pk=sv.pk))
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        wf.save_sample(sv, user, fields={k: form.cleaned_data[k] for k in form.Meta.fields})
        return 'sample', f'Đã lưu tiến độ mẫu {sv.label}.'
    if action == 'techpack_save':
        sv = get_object_or_404(SampleVersion, pk=post.get('sample_version_id'), dossier=dossier)
        form = f.TechPackForm(post)
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        wf.save_tech_pack(sv, user, fields={k: form.cleaned_data[k] for k in form.Meta.fields},
                          lines=_material_lines(post))
        return 'technical', f'Đã lưu hồ sơ kỹ thuật mẫu {sv.label}.'
    if action == 'sample_submit':
        wf.submit_sample(dossier, user, due_at=due)
        return 'sample', 'Đã gửi mẫu đi đánh giá.'
    if action == 'evaluation_add':
        form = f.EvaluationForm(post, allowed_roles=wf.evaluator_roles_for(dossier, user))
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        items = {}
        for key, _label in Criterion.choices:
            res = post.get(f'crit_{key}') or EvaluationItem.RESULT_NA
            if res not in (EvaluationItem.RESULT_PASS, EvaluationItem.RESULT_FAIL, EvaluationItem.RESULT_NA):
                res = EvaluationItem.RESULT_NA
            items[key] = (res, (post.get(f'crit_note_{key}') or '').strip()[:255])
        data = form.cleaned_data
        wf.add_evaluation(dossier, user, role=data['role'], result=data['result'], conclusion=data['conclusion'],
                          defects=data['defects'], fix_owner=data['fix_owner'], fix_due=data['fix_due'], items=items)
        upload = request.FILES.get('evaluation_file')
        if upload:
            wf.upload_attachment(dossier, user, uploaded_file=upload, kind=AttachmentKind.EVALUATION,
                                 sample_version=dossier.current_sample_version())
        return 'sample', 'Đã lưu đánh giá mẫu.'
    if action == 'fix_done':
        ev = get_object_or_404(SampleEvaluation, pk=post.get('evaluation_id'), sample_version__dossier=dossier)
        wf.complete_fix(ev, user, note=post.get('note', ''))
        return 'sample', 'Đã xác nhận sửa lỗi mẫu.'
    if action == 'sample_fix':
        wf.request_sample_fix(dossier, user, comment=comment, due_at=due)
        return 'sample', 'Đã yêu cầu sửa mẫu — mở lần mẫu mới.'
    if action == 'master_submit':
        wf.submit_master(dossier, user, due_at=due)
        return 'approval', 'Đã trình duyệt mẫu chuẩn.'
    if action == 'master_decide':
        decision = post.get('decision', '')
        if decision == 'request_fix':
            wf.request_sample_fix(dossier, user, comment=comment, due_at=due)
            return 'sample', 'Đã yêu cầu sửa mẫu.'
        if decision == 'request_design':
            wf.request_design_change_from_sample(dossier, user, comment=comment, due_at=due)
            return 'design', 'Đã yêu cầu chỉnh thiết kế — mở phiên bản thiết kế mới.'
        if decision == ApprovalDecision.CANCELLED:
            wf.cancel(dossier, user, reason=comment, stage=ApprovalStage.MASTER)
            return 'overview', 'Đã hủy hồ sơ.'
        if decision != ApprovalDecision.APPROVED:
            raise wf.WorkflowError('Quyết định không hợp lệ.')
        wf.decide_master(dossier, user, official_code=post.get('official_code', ''), comment=comment,
                         conditions=_conditions(post), due_at=due)
        return 'approval', 'Đã duyệt mẫu chuẩn.'
    if action == 'condition_done':
        cond = get_object_or_404(ApprovalCondition, pk=post.get('condition_id'), dossier=dossier)
        wf.complete_condition(cond, user, note=post.get('note', ''))
        return 'approval', 'Đã xác nhận hoàn thành điều kiện.'

    if action == 'handover':
        form = f.HandoverForm(post)
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        record = wf.handover(dossier, user, receivers=form.receivers(), note=form.cleaned_data['note'], due_at=due)
        return 'overview', f'Đã bàn giao — tạo hồ sơ kỹ thuật SX {record.product_code}.'
    if action == 'receipt_confirm':
        receipt = get_object_or_404(HandoverReceipt, pk=post.get('receipt_id'), handover__dossier=dossier)
        wf.confirm_receipt(receipt, user, note=post.get('note', ''))
        return 'overview', 'Đã xác nhận nhận bàn giao.'
    if action == 'close':
        wf.close_dossier(dossier, user)
        return 'overview', 'Đã đóng hồ sơ.'

    if action == 'pause':
        wf.pause(dossier, user, reason=comment)
        return 'overview', 'Đã tạm dừng hồ sơ.'
    if action == 'resume':
        wf.resume(dossier, user, comment=comment, due_at=due)
        return 'overview', 'Hồ sơ đã tiếp tục.'
    if action == 'cancel':
        wf.cancel(dossier, user, reason=comment)
        return 'overview', 'Đã hủy hồ sơ.'
    if action == 'change_request':
        wf.request_change_after_approval(dossier, user, target=post.get('target', ''), reason=comment, due_at=due)
        return 'overview', 'Đã mở phiên bản mới theo yêu cầu thay đổi.'

    if action == 'roles_save':
        form = f.RolesForm(post, dossier=dossier)
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        wf.update_roles(dossier, user, assignments=dict(form.cleaned_data))
        return 'overview', 'Đã cập nhật nhân sự hồ sơ.'
    if action == 'member_add':
        member_id = post.get('member_id') or ''
        member = f.active_users().filter(pk=int(member_id)).first() if member_id.isdigit() else None
        wf.add_member(dossier, user, member=member, group=post.get('group', ''))
        return post.get('return_tab') or 'overview', 'Đã thêm thành viên hồ sơ.'
    if action == 'member_remove':
        member = get_object_or_404(DossierMember, pk=post.get('member_pk'), dossier=dossier)
        wf.remove_member(member, user)
        return post.get('return_tab') or 'overview', 'Đã bớt thành viên hồ sơ.'
    if action == 'costing_save':
        form = f.CostingForm(post, instance=ProductDevelopment.objects.get(pk=dossier.pk))
        if not form.is_valid():
            raise wf.WorkflowError(_form_error_text(form))
        wf.update_costing(dossier, user, fields=dict(form.cleaned_data))
        return 'costing', 'Đã lưu giá thành.'
    if action == 'comment_add':
        scope = post.get('scope', '')
        dv = sv = None
        if scope.startswith('d') and scope[1:].isdigit():
            dv = DesignVersion.objects.filter(pk=int(scope[1:]), dossier=dossier).first()
        elif scope.startswith('s') and scope[1:].isdigit():
            sv = SampleVersion.objects.filter(pk=int(scope[1:]), dossier=dossier).first()
        wf.add_comment(dossier, user, body=post.get('body', ''), design_version=dv, sample_version=sv)
        return post.get('return_tab') or 'files', 'Đã gửi trao đổi.'

    if action == 'task_accept':
        wf.accept_task(_task_of(dossier, post), user)
        return post.get('return_tab') or 'overview', 'Đã nhận việc.'
    if action == 'task_delay':
        wf.set_delay_reason(_task_of(dossier, post), user, reason=post.get('reason', ''))
        return 'overview', 'Đã ghi nhận nguyên nhân chậm.'
    if action == 'task_due':
        wf.update_task_due(_task_of(dossier, post), user, due_at=due)
        return 'overview', 'Đã đổi hạn công việc.'

    raise Http404('Thao tác không tồn tại')


@login_required
@require_POST
def dossier_action(request, pk, action):
    dossier = _get_dossier(pk)
    try:
        tab, message = _run_action(request, dossier, action)
    except wf.WorkflowError as exc:
        messages.error(request, str(exc))
        tab = request.POST.get('return_tab') or ''
    else:
        messages.success(request, message)
    if tab not in TAB_KEYS:
        tab = ''
    next_url = request.POST.get('next') or ''
    if next_url.startswith('/thiet-ke-san-pham/') and not next_url.startswith('//'):
        return redirect(next_url)
    return _redirect_tab(dossier, tab)


# ---------------------------------------------------------------------------
# Tệp
# ---------------------------------------------------------------------------

@login_required
@require_POST
def attachment_upload(request, pk):
    dossier = _get_dossier(pk)
    user = request.user
    post = request.POST
    kind = post.get('kind', '')
    dv = sv = cw = None
    if post.get('design_version_id'):
        dv = get_object_or_404(DesignVersion, pk=post['design_version_id'], dossier=dossier)
    if post.get('sample_version_id'):
        sv = get_object_or_404(SampleVersion, pk=post['sample_version_id'], dossier=dossier)
    if post.get('colorway_id'):
        cw = get_object_or_404(Colorway, pk=post['colorway_id'], design_version__dossier=dossier)
    files = request.FILES.getlist('files')
    tab = post.get('return_tab') or 'files'
    if not files:
        messages.error(request, 'Chọn tệp cần tải lên.')
        return _redirect_tab(dossier, tab)
    done = 0
    for upload in files:
        try:
            wf.upload_attachment(dossier, user, uploaded_file=upload, kind=kind, design_version=dv,
                                 sample_version=sv, colorway=cw, note=post.get('note', ''))
            done += 1
        except wf.WorkflowError as exc:
            messages.error(request, f'{upload.name}: {exc}')
            break
        except OSError:
            messages.error(request, f'{upload.name}: không ghi được lên NAS — kiểm tra kết nối NAS.')
            break
    if done:
        messages.success(request, f'Đã tải lên {done} tệp.')
    return _redirect_tab(dossier, tab if tab in TAB_KEYS else 'files')


@login_required
@require_POST
def attachment_delete(request, att_pk):
    att = get_object_or_404(Attachment.objects.select_related('dossier', 'design_version', 'sample_version'), pk=att_pk)
    try:
        wf.delete_attachment(att, request.user)
        messages.success(request, 'Đã xóa tệp.')
    except wf.WorkflowError as exc:
        messages.error(request, str(exc))
    tab = request.POST.get('return_tab') or 'files'
    return _redirect_tab(att.dossier, tab if tab in TAB_KEYS else 'files')


@login_required
def attachment_serve(request, att_pk):
    att = get_object_or_404(Attachment.objects.select_related('dossier'), pk=att_pk)
    if not perms.can_view_dossier(att.dossier, request.user):
        return HttpResponseForbidden('Không có quyền xem tệp.')
    path = design_file_abs_path(att)
    if not path or not os.path.isfile(path):
        raise Http404('Không tìm thấy tệp trên NAS.')
    name = att.display_name
    content_type = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    inline = request.GET.get('download') != '1' and (
        content_type.startswith('image/') or content_type == 'application/pdf')
    response = FileResponse(open(path, 'rb'), content_type=content_type)
    disposition = 'inline' if inline else 'attachment'
    response['Content-Disposition'] = f"{disposition}; filename*=UTF-8''{quote(name)}"
    return response


# ---------------------------------------------------------------------------
# Việc của tôi / duyệt / thông báo / tổng quan / thiết lập
# ---------------------------------------------------------------------------

QUICK_KINDS = {Status.BRIEF_PENDING: 'brief', Status.DESIGN_PENDING: 'design', Status.MASTER_PENDING: 'master'}


def _prepare_quick(dossiers, user) -> list:
    """Hồ sơ người dùng được ra quyết định ngay trên danh sách (modal duyệt nhanh)."""
    ready = []
    for d in dossiers:
        kind = QUICK_KINDS.get(d.status)
        if not kind or not perms.is_dossier_approver(d, user):
            continue
        d.quick_kind = kind
        d.quick_modal_id = f'tkQuick{d.pk}'
        d.quick_options = []
        d.quick_checklist = []
        if kind == 'design':
            options = [dv for dv in d.current_design_versions() if dv.state == DesignVersion.STATE_SUBMITTED]
            fronts = {
                a.design_version_id: a for a in Attachment.objects.filter(
                    design_version__in=options, kind=AttachmentKind.FRONT, is_current=True, is_deleted=False,
                )
            }
            for dv in options:
                dv.current_atts = {'front': fronts.get(dv.pk)}
            d.quick_options = options
        elif kind == 'master':
            d.quick_checklist = wf.master_checklist(d)
        ready.append(d)
    return ready


def _quick_context(request, dossiers) -> dict:
    setting = sla.get_settings()
    return {
        'quick_dossiers': dossiers,
        'quick_next': request.get_full_path(),
        'sla_due': {s: sla.due_at_for(s, setting=setting) for s in Status.values} if dossiers else {},
    }


@login_required
def my_tasks(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_MY_TASKS):
        return _deny(request, perms.MENU_MY_TASKS)
    base = Task.objects.filter(assignee=user).select_related('dossier', 'receipt', 'condition')
    open_tasks = list(base.filter(state=Task.STATE_OPEN).exclude(
        dossier__status__in=(Status.PAUSED, Status.CANCELLED, Status.CLOSED),
    ).order_by('due_at', 'pk'))
    approval_dossiers = {
        t.dossier_id: t.dossier for t in open_tasks
        if t.role == Role.APPROVER and t.step == t.dossier.status
    }
    quick = _prepare_quick(approval_dossiers.values(), user)
    quick_ids = {d.pk: d.quick_modal_id for d in quick}
    for t in open_tasks:
        t.quick_id = quick_ids.get(t.dossier_id) if t.role == Role.APPROVER else None
    now = timezone.now()
    soon = now + timedelta(days=1)
    groups = {
        'overdue': [t for t in open_tasks if t.due_at and t.due_at < now],
        'soon': [t for t in open_tasks if t.due_at and now <= t.due_at < soon],
        'later': [t for t in open_tasks if not t.due_at or t.due_at >= soon],
    }
    recent_done = list(base.filter(state=Task.STATE_DONE).order_by('-completed_at')[:15])
    return render(request, 'thiet_ke_sp/my_tasks.html', _common(
        request, groups=groups, open_count=len(open_tasks), recent_done=recent_done,
        **_quick_context(request, quick),
    ))


@login_required
def approve_queue(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_APPROVE):
        return _deny(request, perms.MENU_APPROVE)
    scope = request.GET.get('scope') or 'mine'
    qs = _annotated_list_qs().filter(status__in=presenters.APPROVAL_STATUSES + (Status.PAUSED,))
    if scope != 'all' or not perms.is_admin(user):
        scope = 'mine'
        qs = qs.filter(approver=user)
    rows = _decorate_rows(list(qs.order_by('step_due_at', 'pk')))
    quick = _prepare_quick(rows, user)
    return render(request, 'thiet_ke_sp/approve_queue.html', _common(
        request, rows=rows, scope=scope, is_admin=perms.is_admin(user),
        can_approve=perms.has_approve_permission(user), **_quick_context(request, quick),
    ))


@login_required
def notifications(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_MY_TASKS):
        return _deny(request, perms.MENU_MY_TASKS)
    if request.method == 'POST':
        Notification.objects.filter(user=user, is_read=False).update(is_read=True)
        nt.invalidate_badges(user)
        messages.success(request, 'Đã đánh dấu đọc tất cả.')
        return redirect('thiet_ke_sp:notifications')
    page = Paginator(Notification.objects.filter(user=user).select_related('dossier'), 40).get_page(
        request.GET.get('page'),
    )
    for n in page.object_list:
        n.icon = nt.KIND_ICONS.get(n.kind, 'bi-bell')
    return render(request, 'thiet_ke_sp/notifications.html', _common(request, page_obj=page, query_string=''))


@login_required
def notification_open(request, pk):
    note = get_object_or_404(Notification, pk=pk, user=request.user)
    if not note.is_read:
        note.is_read = True
        note.save(update_fields=['is_read'])
        nt.invalidate_badges(request.user)
    return redirect(note.url or reverse('thiet_ke_sp:notifications'))


@login_required
def dashboard(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_DASHBOARD):
        if perms.can_view_module(user):
            return redirect('thiet_ke_sp:list')
        if user_can_access_resolved_menu(user, M, perms.MENU_MY_TASKS):
            return redirect('thiet_ke_sp:my_tasks')
        return _deny(request, perms.MENU_DASHBOARD)
    data = reports.dashboard_data()
    recent = _annotated_list_qs().filter(is_demo=False).exclude(status__in=(*STOPPED_STATUSES, Status.CLOSED)).order_by(
        F('step_due_at').asc(nulls_last=True), '-updated_at',
    )[:6]
    bars = presenters.stage_bars(data['status_rows'])
    return render(request, 'thiet_ke_sp/dashboard.html', _common(
        request,
        data=data,
        bars=bars,
        active_count=sum(b['count'] for b in bars),
        alerts=presenters.dashboard_alerts(data, user),
        recent=_decorate_rows(list(recent)),
    ))


KANBAN_QUICK = (('', 'Tất cả'), ('mine', 'Của tôi'), ('overdue', 'Quá hạn'))


@login_required
def kanban(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_KANBAN):
        return _deny(request, perms.MENU_KANBAN)
    g = request.GET
    q = (g.get('q') or '').strip()
    quick = (g.get('quick') or '').strip()
    group = (g.get('group') or '').strip()
    collection = (g.get('collection') or '').strip()
    owner_id = (g.get('owner') or '').strip()

    qs = _annotated_list_qs().filter(status__in=presenters.KANBAN_STATUSES)
    if q:
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(official_product_code__icontains=q))
    if group in ProductGroup.values:
        qs = qs.filter(product_group=group)
    if collection:
        qs = qs.filter(collection=collection)
    if owner_id.isdigit():
        qs = qs.filter(owner_id=int(owner_id))
    if quick in ('mine', 'overdue'):
        qs = _apply_quick(qs, quick, user)
    rows = _decorate_rows(list(qs.order_by(F('step_due_at').asc(nulls_last=True), 'pk')))
    for d in rows:
        d.kanban_moves_json = json.dumps(presenters.kanban_moves(d, user))
    columns = presenters.kanban_columns(rows)
    move_specs = {
        key: {'label': label, 'comment': needs_comment, 'code': needs_code}
        for key, (label, needs_comment, needs_code) in presenters.KANBAN_MOVE_SPECS.items()
    }
    return render(request, 'thiet_ke_sp/kanban.html', _common(
        request,
        columns=columns,
        move_specs=move_specs,
        total_count=len(rows),
        late_count=sum(c['late'] for c in columns),
        quick_filters=KANBAN_QUICK,
        filter_q=q, filter_quick=quick, filter_group=group,
        filter_collection=collection, filter_owner=owner_id,
        has_filters=any([q, quick, group, collection, owner_id]),
        group_choices=ProductGroup.choices,
        collection_choices=_collection_choices(),
        owner_choices=_people_with('tksp_owned'),
    ))


def _run_kanban_move(dossier, user, move: str, *, comment: str, official_code: str) -> None:
    approved, change = ApprovalDecision.APPROVED, ApprovalDecision.REQUEST_CHANGE
    runners = {
        'submit_brief': lambda: wf.submit_brief(dossier, user),
        'brief_approve': lambda: wf.decide_brief(dossier, user, decision=approved, comment=comment),
        'brief_request_change': lambda: wf.decide_brief(dossier, user, decision=change, comment=comment),
        'design_submit': lambda: wf.submit_design(dossier, user),
        'design_approve': lambda: wf.decide_design(dossier, user, decision=approved, comment=comment),
        'design_request_change': lambda: wf.decide_design(dossier, user, decision=change, comment=comment),
        'sample_submit': lambda: wf.submit_sample(dossier, user),
        'master_submit': lambda: wf.submit_master(dossier, user),
        'sample_fix': lambda: wf.request_sample_fix(dossier, user, comment=comment),
        'master_request_fix': lambda: wf.request_sample_fix(dossier, user, comment=comment),
        'master_approve': lambda: wf.decide_master(dossier, user, official_code=official_code, comment=comment),
        'eval_request_design': lambda: wf.request_design_change_from_sample(dossier, user, comment=comment),
        'master_request_design': lambda: wf.request_design_change_from_sample(dossier, user, comment=comment),
        'pause': lambda: wf.pause(dossier, user, reason=comment),
        'resume': lambda: wf.resume(dossier, user, comment=comment),
    }
    if move in ('design_approve', 'design_request_change') and len(dossier.current_design_versions()) > 1:
        raise wf.WorkflowError('Hồ sơ có nhiều phương án thiết kế — mở hồ sơ để chọn phương án.')
    runners[move]()


@login_required
@require_POST
def kanban_move(request, pk):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_KANBAN):
        return _deny(request, perms.MENU_KANBAN)
    dossier = _get_dossier(pk)
    post = request.POST
    next_url = post.get('next') or ''
    if not next_url.startswith('/thiet-ke-san-pham/') or next_url.startswith('//'):
        next_url = reverse('thiet_ke_sp:kanban')
    target = post.get('to', '')
    target_label = presenters.KANBAN_LABELS.get(target, target)
    if post.get('from') and post.get('from') != dossier.status:
        messages.error(request, f'«{dossier.name}» vừa đổi trạng thái — đã tải lại bảng.')
        return redirect(next_url)
    move = presenters.kanban_moves_for_status(dossier).get(target)
    if not move:
        messages.error(request, f'Không chuyển thẳng «{dossier.name}» sang «{target_label}».')
        return redirect(next_url)
    try:
        _run_kanban_move(
            dossier, user, move,
            comment=(post.get('comment') or '').strip(),
            official_code=(post.get('official_code') or '').strip(),
        )
    except wf.WorkflowError as exc:
        messages.error(request, f'«{dossier.name}»: {exc}')
    else:
        messages.success(request, f'«{dossier.name}»: {presenters.KANBAN_MOVE_SPECS[move][0]} — chuyển sang «{target_label}».')
    return redirect(next_url)


@login_required
def report(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_REPORTS):
        return _deny(request, perms.MENU_REPORTS)
    group = (request.GET.get('group') or '').strip()
    collection = (request.GET.get('collection') or '').strip()
    if group not in ProductGroup.values:
        group = ''
    data = reports.report_data(collection=collection, group=group)
    return render(request, 'thiet_ke_sp/reports.html', _common(
        request,
        data=data,
        filter_group=group,
        filter_collection=collection,
        has_filters=bool(group or collection),
        group_choices=ProductGroup.choices,
        collection_choices=_collection_choices(),
    ))


@login_required
def module_settings(request):
    user = request.user
    if not user_can_access_resolved_menu(user, M, perms.MENU_SETTINGS):
        return _deny(request, perms.MENU_SETTINGS)
    setting = sla.get_settings()
    can_edit = perms.can_manage_settings(user)
    form = f.SettingsForm(request.POST or None, setting=setting)
    if request.method == 'POST':
        if not can_edit:
            return _deny(request, perms.MENU_SETTINGS)
        if form.is_valid():
            form.save(user)
            messages.success(request, 'Đã lưu thiết lập.')
            return redirect('thiet_ke_sp:settings')
        messages.error(request, _form_error_text(form))
    return render(request, 'thiet_ke_sp/settings.html', _common(request, form=form, can_edit=can_edit, setting=setting))
