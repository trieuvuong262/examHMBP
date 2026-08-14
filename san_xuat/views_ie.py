"""Giao diện web cho Master Data mã công đoạn sản xuất (IE).

- Trang tổng quan + import/export file Excel.
- Thư viện công đoạn chuẩn.
- Routing mã hàng (danh sách + chi tiết).
"""

from __future__ import annotations

from decimal import Decimal

from django.http import JsonResponse
from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.views.decorators.http import require_GET

from assessment.decorators import module_perm_required
from hrm.menu_permissions import (
    handle_menu_access_denied,
    menu_perm_context,
    user_can_export_menu,
)
from hrm.module_permissions import MODULE_SAN_XUAT
from PortalJustPlay.pagination import paginate_queryset
from san_xuat.list_grid import sx_list_grid_context

from san_xuat.ie_models import (
    SxIeAuditLog,
    SxOperation,
    SxOperationGroup,
    SxProcessStage,
    SxProductPart,
    SxRouting,
    SxRoutingLine,
    SxSkillLevel,
    SxSmvBasis,
    SxSmvSource,
    SxStitchClass,
    ensure_process_stage_defaults,
    ensure_skill_levels_abc,
    ensure_smv_basis_defaults,
    default_smv_basis_name,
)
from san_xuat.services.production_machines import (
    ie_machine_options,
    ie_machine_search,
    production_machine_count,
)
from san_xuat.ie_permissions import (
    IE_APPROVER_GROUP,
    ensure_ie_approver_group,
    ie_approver_group_has_members,
    ie_user_display_name,
    user_can_approve_ie,
)
from san_xuat.services.ie_ops import (
    IeOpsError,
    approve_operation,
    approve_routing,
    reject_operation,
    build_ie_dashboard,
    clone_routing_revision,
    create_blank_operation,
    create_operation_group,
    delete_operation,
    delete_operation_group,
    delete_routing,
    delete_routing_line,
    enrich_routing_lines_from_library,
    is_routing_locked,
    operation_library_snapshot,
    reject_routing,
    resolve_operation,
    save_routing_line_explanations,
    update_operation,
    update_operation_group,
    update_routing_header,
    upsert_routing_line,
)
from san_xuat.services.ie_ref_catalog_io import (
    RefCatalogImportError,
    export_ref_catalog_response,
    import_ref_catalog,
    ref_catalog_io_meta,
)
from san_xuat.services.operation_master import (
    KIND_GROUPS,
    KIND_LIBRARY,
    KIND_ROUTING,
    OperationMasterImportError,
    export_ie_dataset_response,
    export_operation_master_response,
    ie_dataset_meta,
    import_ie_dataset,
    normalize_ie_kind,
)

IE_MENU_KEY = 'ie'
IE_APPROVE_MENU_KEY = 'ie_approve'
IE_SETTINGS_MENU_KEY = 'ie_settings'


def _ie_io_context(kind: str) -> dict:
    meta = ie_dataset_meta(kind)
    return {
        'ie_kind': meta['kind'],
        'ie_io': meta,
    }


def _ref_io_context(kind: str) -> dict:
    meta = ref_catalog_io_meta(kind)
    return {
        'ref_kind': meta['kind'],
        'ref_io': meta,
    }


def _perm_ctx(request):
    return {
        **menu_perm_context(request.user, MODULE_SAN_XUAT, IE_MENU_KEY),
        'can_approve': user_can_approve_ie(request.user),
        'approver_group_ready': ie_approver_group_has_members(),
        'approver_group_name': IE_APPROVER_GROUP,
    }


def _settings_perm_ctx(request):
    return menu_perm_context(request.user, MODULE_SAN_XUAT, IE_SETTINGS_MENU_KEY)


def _require_ie_approve_access(request):
    from hrm.menu_permissions import user_can_access_menu

    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, IE_APPROVE_MENU_KEY):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, IE_APPROVE_MENU_KEY)
    return None


def _approve_perm_ctx(request):
    return {
        'can_approve': user_can_approve_ie(request.user),
        'approver_group_ready': ie_approver_group_has_members(),
        'approver_group_name': IE_APPROVER_GROUP,
    }


IE_APPROVE_KIND_ALL = 'all'
IE_APPROVE_KIND_OPERATION = 'cong-doan'
IE_APPROVE_KIND_ROUTING = 'routing'
IE_APPROVE_KINDS = (IE_APPROVE_KIND_ALL, IE_APPROVE_KIND_OPERATION, IE_APPROVE_KIND_ROUTING)

IE_APPROVE_STATUS_PENDING = 'pending'
IE_APPROVE_STATUS_APPROVED = 'approved'
IE_APPROVE_STATUS_REJECTED = 'rejected'
IE_APPROVE_STATUS_ALL = 'all'
IE_APPROVE_STATUS_CHOICES = (
    (IE_APPROVE_STATUS_PENDING, 'Chưa duyệt'),
    (IE_APPROVE_STATUS_APPROVED, 'Đã duyệt'),
    (IE_APPROVE_STATUS_REJECTED, 'Từ chối'),
    (IE_APPROVE_STATUS_ALL, 'Tất cả'),
)
IE_APPROVE_STATUSES = tuple(v for v, _ in IE_APPROVE_STATUS_CHOICES)


def _operations_qs_for_approval(status: str = IE_APPROVE_STATUS_PENDING):
    qs = SxOperation.objects.select_related('group').exclude(status=SxOperation.STATUS_RETIRED)
    if status == IE_APPROVE_STATUS_APPROVED:
        qs = qs.filter(status=SxOperation.STATUS_APPROVED, approved_at__isnull=False)
    elif status == IE_APPROVE_STATUS_REJECTED:
        qs = qs.none()
    elif status == IE_APPROVE_STATUS_ALL:
        return qs
    else:
        # Chưa duyệt trên Portal: nháp/thử nghiệm, hoặc Excel gắn "Đã duyệt" nhưng chưa có mốc duyệt.
        qs = qs.filter(
            Q(status__in=(SxOperation.STATUS_DRAFT, SxOperation.STATUS_TRIAL))
            | Q(approved_at__isnull=True)
        )
    return qs


def _routings_qs_for_approval(status: str = IE_APPROVE_STATUS_PENDING):
    qs = SxRouting.objects.annotate(
        n_lines=Count('lines'),
        sum_smv=Sum('lines__total_operation_smv'),
    )
    if status == IE_APPROVE_STATUS_APPROVED:
        qs = qs.filter(approval_status=SxRouting.APPROVAL_APPROVED)
    elif status == IE_APPROVE_STATUS_REJECTED:
        qs = qs.filter(approval_status=SxRouting.APPROVAL_REJECTED)
    elif status == IE_APPROVE_STATUS_ALL:
        return qs
    else:
        qs = qs.filter(
            approval_status__in=(SxRouting.APPROVAL_DRAFT, SxRouting.APPROVAL_PENDING),
        )
    return qs


def _filter_operations_for_approval(term: str = '', status: str = IE_APPROVE_STATUS_PENDING):
    qs = _operations_qs_for_approval(status)
    if term:
        qs = qs.filter(
            Q(op_code__icontains=term)
            | Q(name_vi__icontains=term)
            | Q(ie_owner__icontains=term)
            | Q(group__code__icontains=term)
        )
    return qs.order_by('op_code', 'op_rev')


def _filter_routings_for_approval(term: str = '', status: str = IE_APPROVE_STATUS_PENDING):
    qs = _routings_qs_for_approval(status)
    if term:
        qs = qs.filter(
            Q(routing_id__icontains=term)
            | Q(style_code__icontains=term)
            | Q(style_name__icontains=term)
            | Q(ie_owner__icontains=term)
        )
    return qs.order_by('style_code', 'routing_rev')


def _pending_operations_qs():
    return _operations_qs_for_approval(IE_APPROVE_STATUS_PENDING)


def _pending_routings_qs():
    return _routings_qs_for_approval(IE_APPROVE_STATUS_PENDING)


def _bulk_approve_reject(*, request, action: str, op_pks: list[int], routing_pks: list[int], perms: dict):
    if not perms['can_approve']:
        raise IeOpsError('Bạn không có quyền duyệt (cần quyền Sửa menu Duyệt phát hành).')
    ok_ops = ok_rt = 0
    errors = []
    ops = {op.pk: op for op in SxOperation.objects.filter(pk__in=op_pks)}
    for pk in op_pks:
        op = ops.get(pk)
        if not op:
            continue
        try:
            if action == 'bulk_approve':
                approve_operation(operation=op, user=request.user)
            else:
                reject_operation(operation=op, user=request.user)
            ok_ops += 1
        except IeOpsError as exc:
            errors.append(str(exc))
    locked = _locked_routing_ids()
    routings = {r.pk: r for r in SxRouting.objects.filter(pk__in=routing_pks)}
    for pk in routing_pks:
        routing = routings.get(pk)
        if not routing:
            continue
        try:
            if action == 'bulk_approve':
                if routing.pk in locked:
                    raise IeOpsError(f'Routing {routing.routing_id} đã khóa — tạo REV mới.')
                approve_routing(routing=routing, user=request.user)
            else:
                if routing.approval_status == SxRouting.APPROVAL_REJECTED:
                    raise IeOpsError(f'Routing {routing.routing_id} đã bị từ chối.')
                reject_routing(routing=routing, user=request.user)
            ok_rt += 1
        except IeOpsError as exc:
            errors.append(str(exc))
    verb = 'duyệt' if action == 'bulk_approve' else 'từ chối'
    parts = []
    if ok_ops:
        parts.append(f'{ok_ops} công đoạn')
    if ok_rt:
        parts.append(f'{ok_rt} routing')
    if parts:
        messages.success(request, f'Đã {verb} {", ".join(parts)}.')
    for msg in errors[:5]:
        messages.error(request, msg)
    if len(errors) > 5:
        messages.error(request, f'… và {len(errors) - 5} lỗi khác.')


def _parse_approve_pks(raw_pks: list[str], *, kind: str) -> tuple[list[int], list[int]]:
    op_pks: list[int] = []
    rt_pks: list[int] = []
    for raw in raw_pks:
        val = (raw or '').strip()
        if not val:
            continue
        if val.startswith('op:') and val[3:].isdigit():
            op_pks.append(int(val[3:]))
        elif val.startswith('rt:') and val[3:].isdigit():
            rt_pks.append(int(val[3:]))
        elif val.isdigit():
            pk = int(val)
            if kind == IE_APPROVE_KIND_ROUTING:
                rt_pks.append(pk)
            else:
                op_pks.append(pk)
    return op_pks, rt_pks


def _ie_approve_hub_url(*, kind: str = '', term: str = '', status: str = '', page: str = '') -> str:
    params = {}
    if kind in IE_APPROVE_KINDS and kind != IE_APPROVE_KIND_ALL:
        params['kind'] = kind
    if status and status != IE_APPROVE_STATUS_PENDING:
        params['status'] = status
    if term:
        params['q'] = term
    if page:
        params['page'] = page
    base = reverse('san_xuat:ie_approve_hub')
    return f'{base}?{urlencode(params)}' if params else base


def _locked_routing_ids():
    from san_xuat.hub_models import SxProductionOrder

    return set(
        SxProductionOrder.objects.filter(routing_id__isnull=False).values_list('routing_id', flat=True)
    )


def _approve_row_operation(op) -> dict:
    smv = op.base_smv_min or Decimal('0')
    extra_badges = []
    portal_approved = (
        op.status == SxOperation.STATUS_APPROVED and op.approved_at is not None
    )
    if portal_approved:
        approval_label = 'Đã duyệt'
        approval_badge = 'success'
        can_select = False
    else:
        approval_label = 'Chưa duyệt'
        approval_badge = 'warning'
        can_select = True
    return {
        'item_kind': 'op',
        'pk_value': f'op:{op.pk}',
        'type_label': 'Công đoạn',
        'code': op.op_code,
        'code_url': reverse('san_xuat:ie_operation_detail', args=[op.pk]),
        'rev': op.op_rev,
        'name': op.name_vi,
        'detail': op.group.code if op.group_id else '—',
        'smv': smv,
        'approval_label': approval_label,
        'approval_badge': approval_badge,
        'owner': op.ie_owner or '—',
        'can_select': can_select,
        'extra_badges': extra_badges,
        'view_url': reverse('san_xuat:ie_operation_detail', args=[op.pk]),
        'view_label': 'Xem',
    }


def _approve_row_routing(r, locked_ids: set) -> dict:
    is_locked = r.pk in locked_ids
    if r.approval_status == SxRouting.APPROVAL_REJECTED:
        approval_label = 'Từ chối'
        approval_badge = 'secondary'
        can_select = False
    elif r.approval_status == SxRouting.APPROVAL_APPROVED:
        approval_label = 'Đã duyệt'
        approval_badge = 'success'
        can_select = False
    else:
        approval_label = 'Chưa duyệt'
        approval_badge = 'warning'
        can_select = not is_locked
    extra_badges = []
    if is_locked:
        extra_badges.append(('Đã khóa', 'warning'))
    return {
        'item_kind': 'rt',
        'pk_value': f'rt:{r.pk}',
        'type_label': 'Routing',
        'code': r.routing_id,
        'code_url': reverse('san_xuat:ie_routing_detail', args=[r.pk]),
        'rev': r.routing_rev,
        'name': r.style_name or '—',
        'detail': r.style_code,
        'smv': r.sum_smv,
        'n_lines': r.n_lines,
        'approval_label': approval_label,
        'approval_badge': approval_badge,
        'owner': r.ie_owner or '—',
        'can_select': can_select,
        'extra_badges': extra_badges,
        'view_url': reverse('san_xuat:ie_routing_detail', args=[r.pk]),
        'view_label': 'Xem',
    }


def _build_approve_rows(*, operations=(), routings=(), locked_ids: set | None = None) -> list[dict]:
    locked_ids = locked_ids or set()
    rows = [_approve_row_operation(op) for op in operations]
    rows.extend(_approve_row_routing(r, locked_ids) for r in routings)
    return rows


def _require_ie_menu(request):
    from hrm.menu_permissions import user_can_access_menu

    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, IE_MENU_KEY):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, IE_MENU_KEY)
    return None


def _create_routing_then_detail(
    request,
    *,
    style_code: str,
    style_name: str = '',
    routing_rev: str = 'R01',
    fail_redirect: str = 'san_xuat:ie_routing_list',
):
    perms = _perm_ctx(request)
    if not (perms['can_create'] or perms['can_update']):
        messages.error(request, 'Bạn không có quyền tạo routing.')
        return redirect(fail_redirect)
    from san_xuat.services.ie_ops import create_blank_routing

    style_code = (style_code or '').strip()
    style_name = (style_name or '').strip()
    routing_rev = (routing_rev or 'R01').strip() or 'R01'
    if not style_code:
        messages.error(request, 'Chọn mã hàng từ kho sản phẩm.')
        return redirect(fail_redirect)
    from san_xuat.models import ProductTechDoc
    from san_xuat.services.products import resolve_product_ref

    ref = resolve_product_ref(style_code)
    tech_doc = ProductTechDoc.objects.filter(product_code__iexact=style_code).first()
    if ref:
        style_code = ref.code
        if not style_name:
            style_name = ref.name
        if tech_doc is None:
            tech_doc = ProductTechDoc.objects.filter(product_code__iexact=ref.code).first()
    elif tech_doc:
        style_code = tech_doc.product_code
        if not style_name:
            style_name = tech_doc.product_name
    else:
        messages.error(request, f'Mã hàng {style_code} không có trong kho sản phẩm.')
        return redirect(fail_redirect)
    seed = f'{style_code}-{routing_rev}'
    try:
        routing = create_blank_routing(
            style_code=seed,
            routing_id=seed,
            style_name=style_name,
            tech_doc=tech_doc,
            user=request.user,
        )
    except IeOpsError as exc:
        messages.error(request, str(exc))
        return redirect(fail_redirect)
    messages.success(request, f'Đã tạo routing {routing.routing_id}.')
    url = reverse('san_xuat:ie_routing_detail', args=[routing.pk])
    return redirect(f'{url}#ie-routing-line-form')


def _create_routing_from_post(request, *, fail_redirect: str):
    return _create_routing_then_detail(
        request,
        style_code=(request.POST.get('style_code') or '').strip(),
        style_name=(request.POST.get('style_name') or '').strip(),
        routing_rev=(request.POST.get('routing_rev') or 'R01').strip() or 'R01',
        fail_redirect=fail_redirect,
    )


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_create(request):
    """Tạo routing trống rồi vào màn thêm công đoạn (không qua danh sách)."""
    denied = _require_ie_menu(request)
    if denied:
        return denied
    return _create_routing_then_detail(
        request,
        style_code=(request.GET.get('style_code') or '').strip(),
        style_name=(request.GET.get('style_name') or '').strip(),
        routing_rev=(request.GET.get('routing_rev') or 'R01').strip() or 'R01',
    )


def _dec(raw, default='0'):
    from decimal import Decimal, InvalidOperation
    try:
        return Decimal(str(raw if raw not in (None, '') else default))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def _ie_operation_form_catalogs(*, extra_product_part: str = ''):
    """Danh mục dropdown form công đoạn (tạo / sửa)."""
    product_parts = list(
        SxProductPart.objects.filter(is_active=True)
        .order_by('sort_order', 'code')
        .values_list('name', flat=True)
    )
    if extra_product_part and extra_product_part not in product_parts:
        product_parts = [extra_product_part] + product_parts
    smv_bases = ensure_smv_basis_defaults()
    return {
        'process_stages': ensure_process_stage_defaults(),
        'skill_levels': ensure_skill_levels_abc(),
        'stitch_classes': SxStitchClass.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'smv_sources': SxSmvSource.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'product_parts': product_parts,
        'smv_basis_choices': [b.name for b in smv_bases],
        'default_smv_basis': default_smv_basis_name(),
    }


def _handle_ie_import(request, *, redirect_to, kind: str = KIND_LIBRARY):
    """Xử lý POST action=import — theo từng loại (nhóm / thư viện / routing)."""
    perms = _perm_ctx(request)
    if not (perms['can_create'] or perms['can_update']):
        messages.error(request, 'Bạn không có quyền import dữ liệu.')
        return redirect(redirect_to)
    upload = request.FILES.get('excel_file')
    if not upload:
        messages.error(request, 'Chưa chọn file Excel.')
        return redirect(redirect_to)
    if not upload.name.lower().endswith(('.xlsx', '.xlsm')):
        messages.error(request, 'File phải là định dạng .xlsx.')
        return redirect(redirect_to)
    dry_run = request.POST.get('dry_run') == '1'
    post_kind = (request.POST.get('ie_kind') or kind or '').strip()
    try:
        kind = normalize_ie_kind(post_kind)
        result = import_ie_dataset(upload, kind, dry_run=dry_run, user=request.user)
        label = ie_dataset_meta(kind)['label']
    except OperationMasterImportError as exc:
        messages.error(request, f'Lỗi import: {exc}')
        return redirect(redirect_to)

    prefix = 'THỬ (không lưu) — ' if dry_run else ''
    summary = ', '.join(f'{k}: {v}' for k, v in sorted(result.created.items())) or 'không có bản ghi mới'
    messages.success(
        request,
        f'{prefix}Import {label} xong. Tạo mới {result.total_created}, '
        f'cập nhật {result.total_updated}. Chi tiết: {summary}.',
    )
    for w in result.warnings[:15]:
        messages.warning(request, w)
    if len(result.warnings) > 15:
        messages.warning(request, f'… và {len(result.warnings) - 15} cảnh báo khác.')
    return redirect(redirect_to)


def _handle_ref_catalog_import(request, *, kind: str, redirect_to: str):
    """Xử lý POST action=import trên trang danh mục thiết lập IE."""
    perms = _settings_perm_ctx(request)
    if not (perms['can_create'] or perms['can_update']):
        messages.error(request, 'Bạn không có quyền import dữ liệu.')
        return redirect(redirect_to)
    upload = request.FILES.get('excel_file')
    if not upload:
        messages.error(request, 'Chưa chọn file Excel.')
        return redirect(redirect_to)
    if not upload.name.lower().endswith(('.xlsx', '.xlsm')):
        messages.error(request, 'File phải là định dạng .xlsx.')
        return redirect(redirect_to)
    dry_run = request.POST.get('dry_run') == '1'
    post_kind = (request.POST.get('ref_kind') or kind or '').strip()
    try:
        result = import_ref_catalog(upload, post_kind, dry_run=dry_run, user=request.user)
        label = ref_catalog_io_meta(post_kind)['label']
    except RefCatalogImportError as exc:
        messages.error(request, f'Lỗi import: {exc}')
        return redirect(redirect_to)

    prefix = 'THỬ (không lưu) — ' if dry_run else ''
    summary = ', '.join(f'{k}: {v}' for k, v in sorted(result.created.items())) or 'không có bản ghi mới'
    messages.success(
        request,
        f'{prefix}Import {label} xong. Tạo mới {result.total_created}, '
        f'cập nhật {result.total_updated}. Chi tiết: {summary}.',
    )
    for w in result.warnings[:15]:
        messages.warning(request, w)
    if len(result.warnings) > 15:
        messages.warning(request, f'… và {len(result.warnings) - 15} cảnh báo khác.')
    return redirect(redirect_to)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_hub(request):
    perms = _perm_ctx(request)

    stats = {
        'machines': production_machine_count(),
        'stitch_classes': SxStitchClass.objects.count(),
        'skill_levels': SxSkillLevel.objects.count(),
        'smv_sources': SxSmvSource.objects.count(),
        'process_stages': SxProcessStage.objects.count(),
        'groups': SxOperationGroup.objects.count(),
        'operations': SxOperation.objects.count(),
        'operations_approved': SxOperation.objects.filter(status=SxOperation.STATUS_APPROVED).count(),
        'routings': SxRouting.objects.count(),
        'routing_lines': SxRoutingLine.objects.count(),
    }
    routings = (
        SxRouting.objects.annotate(
            n_lines=Count('lines'),
            sum_smv=Sum('lines__total_operation_smv'),
        ).order_by('style_code', 'routing_rev')
    )
    return render(request, 'san_xuat/ie_hub.html', {
        **perms,
        'stats': stats,
        'routings': routings,
    })


@module_perm_required(MODULE_SAN_XUAT, 'export')
@require_GET
def ie_export(request, kind=None):
    denied = _require_ie_menu(request)
    if denied:
        return denied
    if not user_can_export_menu(request.user, MODULE_SAN_XUAT, IE_MENU_KEY):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, IE_MENU_KEY)
    raw = (kind or request.GET.get('kind') or '').strip().lower()
    if raw in ('', 'master', 'all', 'full'):
        return export_operation_master_response(user=request.user)
    try:
        return export_ie_dataset_response(raw, template=False, user=request.user)
    except OperationMasterImportError as exc:
        messages.error(request, str(exc))
        return redirect('san_xuat:ie_hub')


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def ie_import_template(request, kind=None):
    """File mẫu Excel (1 sheet hướng dẫn + 1 sheet dữ liệu) theo loại."""
    denied = _require_ie_menu(request)
    if denied:
        return denied
    raw = (kind or request.GET.get('kind') or KIND_LIBRARY).strip()
    try:
        return export_ie_dataset_response(raw, template=True)
    except OperationMasterImportError as exc:
        messages.error(request, str(exc))
        return redirect('san_xuat:ie_hub')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def group_list(request):
    perms = _perm_ctx(request)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        back = request.get_full_path() if request.GET else reverse('san_xuat:ie_group_list')
        if action == 'import':
            return _handle_ie_import(request, redirect_to=back, kind=KIND_GROUPS)
        if not (perms['can_create'] or perms['can_update']):
            messages.error(request, 'Bạn không có quyền sửa nhóm công đoạn.')
            return redirect(back)
        pk = (request.POST.get('pk') or '').strip()
        group = SxOperationGroup.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
        try:
            if action == 'create_group':
                from datetime import date as _date_cls

                eff_raw = (request.POST.get('effective_from') or '').strip()
                effective_from = None
                if eff_raw:
                    try:
                        effective_from = _date_cls.fromisoformat(eff_raw)
                    except ValueError as exc:
                        raise IeOpsError('Ngày hiệu lực không hợp lệ (YYYY-MM-DD).') from exc
                group = create_operation_group(
                    code=(request.POST.get('group_code') or '').strip(),
                    name=(request.POST.get('group_name') or '').strip(),
                    process_stage_label=(request.POST.get('process_stage_label') or '').strip(),
                    product_part=(request.POST.get('product_part') or '').strip(),
                    description=(request.POST.get('description') or '').strip(),
                    effective_from=effective_from,
                    is_active=request.POST.get('is_active') == '1',
                    notes=(request.POST.get('notes') or '').strip(),
                    user=request.user,
                )
                messages.success(request, f'Đã tạo nhóm {group.code}.')
            elif action == 'update_group':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa nhóm.')
                if not group:
                    raise IeOpsError('Thiếu nhóm công đoạn.')
                from datetime import date as _date_cls

                eff_raw = (request.POST.get('effective_from') or '').strip()
                effective_from = None
                if eff_raw:
                    try:
                        effective_from = _date_cls.fromisoformat(eff_raw)
                    except ValueError as exc:
                        raise IeOpsError('Ngày hiệu lực không hợp lệ (YYYY-MM-DD).') from exc
                update_operation_group(
                    group=group,
                    name=(request.POST.get('group_name') or '').strip(),
                    process_stage_label=(request.POST.get('process_stage_label') or '').strip(),
                    product_part=(request.POST.get('product_part') or '').strip(),
                    description=(request.POST.get('description') or '').strip(),
                    data_owner=group.data_owner,
                    effective_from=effective_from,
                    is_active=request.POST.get('is_active') == '1',
                    notes=(request.POST.get('notes') or '').strip(),
                )
                messages.success(request, f'Đã lưu nhóm {group.code}.')
            elif action == 'delete_group':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa nhóm.')
                if not group:
                    raise IeOpsError('Thiếu nhóm công đoạn.')
                code = group.code
                delete_operation_group(group=group)
                messages.success(request, f'Đã xóa nhóm {code}.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect(back)

    qs = (
        SxOperationGroup.objects.select_related('default_work_center')
        .annotate(n_ops=Count('operations'))
    )
    active_filter = (request.GET.get('active') or '').strip()
    if active_filter == '1':
        qs = qs.filter(is_active=True)
    elif active_filter == '0':
        qs = qs.filter(is_active=False)
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(code__icontains=term)
            | Q(name__icontains=term)
            | Q(process_stage_label__icontains=term)
            | Q(product_part__icontains=term)
            | Q(description__icontains=term)
            | Q(data_owner__icontains=term)
            | Q(notes__icontains=term)
            | Q(default_work_center__name__icontains=term)
            | Q(default_work_center_code__icontains=term)
        )
    qs = qs.order_by('sort_order', 'code')
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_group_list.html', {
        **perms,
        **_ie_io_context(KIND_GROUPS),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'active_filter': active_filter,
        'total': qs.count(),
        'process_stages': ensure_process_stage_defaults(),
        'current_user_display_name': ie_user_display_name(request.user),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def machine_list(request):
    return redirect('equipment:device_list_production')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_line_list(request):
    perms = _perm_ctx(request)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        back = request.get_full_path() if request.GET else reverse('san_xuat:ie_routing_line_list')
        if action == 'goto_add_line':
            rid = (request.POST.get('routing_id') or '').strip()
            routing = SxRouting.objects.filter(pk=int(rid)).first() if rid.isdigit() else None
            if not routing:
                messages.error(request, 'Chọn routing để thêm dòng.')
                return redirect(back)
            return redirect('san_xuat:ie_routing_detail', pk=routing.pk)
        if action == 'delete_line':
            if not perms['can_update']:
                messages.error(request, 'Bạn không có quyền xóa dòng routing.')
                return redirect(back)
            rid = (request.POST.get('routing_id') or '').strip()
            line_pk = (request.POST.get('line_pk') or '').strip()
            routing = SxRouting.objects.filter(pk=int(rid)).first() if rid.isdigit() else None
            try:
                if not routing or not line_pk.isdigit():
                    raise IeOpsError('Thiếu dòng cần xóa.')
                delete_routing_line(routing=routing, line_pk=int(line_pk))
                messages.success(request, 'Đã xóa dòng routing.')
            except IeOpsError as exc:
                messages.error(request, str(exc))
            return redirect(back)

    qs = SxRoutingLine.objects.select_related('routing', 'operation', 'machine', 'work_center').all()
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(op_code__icontains=term)
            | Q(op_name_vi__icontains=term)
            | Q(routing__style_code__icontains=term)
            | Q(routing__routing_id__icontains=term)
            | Q(machine_code__icontains=term)
            | Q(work_center_code__icontains=term)
            | Q(work_center__name__icontains=term)
        )
    qs = qs.order_by('routing__style_code', 'routing__routing_rev', 'seq_no')
    page_obj, query_string = paginate_queryset(request, qs)
    from san_xuat.hub_models import SxProductionOrder
    locked_routing_ids = set(
        SxProductionOrder.objects.filter(routing_id__isnull=False).values_list('routing_id', flat=True)
    )
    return render(request, 'san_xuat/ie_routing_line_list.html', {
        **perms,
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
        'routings': SxRouting.objects.filter(is_active=True).order_by('style_code', 'routing_rev')[:200],
        'locked_routing_ids': locked_routing_ids,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def operation_list(request):
    perms = _perm_ctx(request)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        back = request.get_full_path() if request.GET else reverse('san_xuat:ie_operation_list')
        if action == 'import':
            return _handle_ie_import(request, redirect_to=back, kind=KIND_LIBRARY)
        pk = request.POST.get('pk')
        op = SxOperation.objects.filter(pk=int(pk)).first() if pk and str(pk).isdigit() else None
        try:
            if action == 'approve_operation' and op:
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền duyệt công đoạn (cần quyền Sửa menu Duyệt phát hành).')
                approve_operation(operation=op, user=request.user)
                messages.success(request, f'Đã duyệt {op.op_code}/{op.op_rev}.')
            elif action == 'create_operation':
                if not (perms['can_create'] or perms['can_update']):
                    raise IeOpsError('Bạn không có quyền tạo công đoạn.')
                from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

                time_sec_raw = (request.POST.get('time_sec') or '').strip()
                try:
                    if time_sec_raw:
                        smv = (Decimal(time_sec_raw) / Decimal('60')).quantize(
                            Decimal('0.0001'), rounding=ROUND_HALF_UP,
                        )
                    else:
                        smv = Decimal('0')
                except (InvalidOperation, ValueError) as exc:
                    raise IeOpsError('Định mức thời gian (giây) không hợp lệ.') from exc
                group = None
                group_id = (request.POST.get('group_id') or '').strip()
                if group_id.isdigit():
                    group = SxOperationGroup.objects.filter(pk=int(group_id)).first()
                if group is None:
                    raise IeOpsError('Chọn nhóm công đoạn.')
                created = create_blank_operation(
                    op_code=(request.POST.get('op_code') or '').strip(),
                    name_vi=(request.POST.get('name_vi') or '').strip(),
                    group=group,
                    op_rev=(request.POST.get('op_rev') or 'R01').strip() or 'R01',
                    base_smv_min=smv,
                    machine_code=(request.POST.get('machine_code') or '').strip(),
                    process_stage_label=(request.POST.get('process_stage_label') or '').strip(),
                    user=request.user,
                )
                update_operation(
                    operation=created,
                    user=request.user,
                    name_en=request.POST.get('name_en'),
                    product_part=request.POST.get('product_part'),
                    method_variant=request.POST.get('method_variant'),
                    skill_level_label=request.POST.get('skill_level_label'),
                    stitch_class_code=request.POST.get('stitch_class_code'),
                    smv_source_code=request.POST.get('smv_source_code'),
                    smv_basis=(request.POST.get('smv_basis') or '').strip() or default_smv_basis_name(),
                    thread_needle=request.POST.get('thread_needle'),
                    attachment_code=request.POST.get('attachment_code'),
                    notes=request.POST.get('notes'),
                    base_smv_min=smv,
                )
                messages.success(request, f'Đã tạo công đoạn {created.op_code}/{created.op_rev}.')
                return redirect('san_xuat:ie_operation_detail', pk=created.pk)
            elif action == 'delete_operation' and op:
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa công đoạn.')
                label = delete_operation(operation=op)
                messages.success(request, f'Đã xóa {label}.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect(back)

    qs = SxOperation.objects.select_related(
        'group', 'machine', 'skill_level', 'stitch_class', 'smv_source',
    ).all()

    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(op_code__icontains=term)
            | Q(name_vi__icontains=term)
            | Q(name_en__icontains=term)
            | Q(machine_code__icontains=term)
        )
    group_code = (request.GET.get('group') or '').strip()
    if group_code:
        qs = qs.filter(group__code=group_code)
    status = (request.GET.get('status') or '').strip()
    if status:
        qs = qs.filter(status=status)
    else:
        # Mặc định ẩn OP đã ngưng — thư viện chỉ hiện bộ chuẩn đang dùng
        qs = qs.exclude(status=SxOperation.STATUS_RETIRED)

    qs = qs.order_by('op_code', 'op_rev')
    grid = sx_list_grid_context(request, 'ie_operation')
    grid['sx_list_storage_key'] = 'san_xuat_ie_operation_cols_v4'
    if not perms.get('can_update'):
        cols = [c for c in grid['list_columns'] if c['key'] != 'actions']
        grid = {
            **grid,
            'list_columns': cols,
            'total_col_weight': sum(c['weight'] for c in cols) or 1,
        }
    return render(request, 'san_xuat/ie_operation_list.html', {
        **perms,
        **_ie_io_context(KIND_LIBRARY),
        **grid,
        'items': qs,
        'term': term,
        'group_code': group_code,
        'status': status,
        'groups': SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'status_choices': SxOperation.STATUS_CHOICES,
        'machines': ie_machine_options(),
        'total': qs.count(),
        'current_user_display_name': ie_user_display_name(request.user),
        **_ie_operation_form_catalogs(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def operation_detail(request, pk: int):
    op = get_object_or_404(
        SxOperation.objects.select_related('group', 'machine', 'skill_level', 'stitch_class', 'smv_source'),
        pk=pk,
    )
    perms = _perm_ctx(request)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'approve_operation':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền duyệt công đoạn.')
                approve_operation(operation=op, user=request.user)
                messages.success(request, f'Đã duyệt {op.op_code}/{op.op_rev}.')
            elif action == 'save_operation':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa công đoạn.')
                group = None
                gid = (request.POST.get('group_id') or '').strip()
                if gid.isdigit():
                    group = SxOperationGroup.objects.filter(pk=int(gid)).first()
                smv_raw = (request.POST.get('base_smv_min') or '').strip()
                smv = _dec(smv_raw) if smv_raw != '' else None
                status = (request.POST.get('status') or '').strip() or None
                from datetime import date as _date_cls

                def _parse_date(raw: str):
                    raw = (raw or '').strip()
                    if not raw:
                        return None, True  # clear
                    try:
                        return _date_cls.fromisoformat(raw), False
                    except ValueError as exc:
                        raise IeOpsError('Ngày không hợp lệ (YYYY-MM-DD).') from exc

                eff_from, clear_from = _parse_date(request.POST.get('effective_from'))
                eff_to, clear_to = _parse_date(request.POST.get('effective_to'))
                update_operation(
                    operation=op,
                    user=request.user,
                    name_vi=request.POST.get('name_vi'),
                    name_en=request.POST.get('name_en'),
                    group=group,
                    process_stage_label=request.POST.get('process_stage_label'),
                    product_part=request.POST.get('product_part'),
                    method_variant=request.POST.get('method_variant'),
                    machine_code=request.POST.get('machine_code'),
                    skill_level_label=request.POST.get('skill_level_label'),
                    stitch_class_code=request.POST.get('stitch_class_code'),
                    smv_source_code=request.POST.get('smv_source_code'),
                    base_smv_min=smv,
                    smv_basis=(request.POST.get('smv_basis') or '').strip() or default_smv_basis_name(),
                    qc_criteria=request.POST.get('qc_criteria'),
                    status=status if status != SxOperation.STATUS_APPROVED else None,
                    ie_owner=op.ie_owner or ie_user_display_name(request.user),
                    revision_reason=request.POST.get('revision_reason'),
                    notes=request.POST.get('notes'),
                    work_instruction_url=request.POST.get('work_instruction_url'),
                    thread_needle=request.POST.get('thread_needle'),
                    attachment_code=request.POST.get('attachment_code'),
                    effective_from=eff_from,
                    effective_to=eff_to,
                    clear_effective_from=clear_from,
                    clear_effective_to=clear_to,
                )
                messages.success(request, f'Đã lưu {op.op_code}/{op.op_rev}.')
            elif action == 'delete_operation':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa công đoạn.')
                label = delete_operation(operation=op)
                messages.success(request, f'Đã xóa {label}.')
                return redirect('san_xuat:ie_operation_list')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect('san_xuat:ie_operation_detail', pk=op.pk)

    product_parts = list(
        SxProductPart.objects.filter(is_active=True)
        .order_by('sort_order', 'code')
        .values_list('name', flat=True)
    )
    # Giữ giá trị đang dùng nếu chưa có trong catalog
    extras = list(
        SxOperation.objects.exclude(product_part='')
        .order_by('product_part')
        .values_list('product_part', flat=True)
        .distinct()
    )
    for p in extras:
        if p and p not in product_parts:
            product_parts.append(p)
    if op.product_part and op.product_part not in product_parts:
        product_parts = [op.product_part] + product_parts
    smv_bases = ensure_smv_basis_defaults()
    smv_basis_choices = [b.name for b in smv_bases]
    if op.smv_basis and op.smv_basis not in smv_basis_choices:
        # Giữ giá trị cũ nếu chưa có trong danh mục
        smv_basis_choices = [op.smv_basis] + smv_basis_choices
    current_owner = ie_user_display_name(request.user)

    return render(request, 'san_xuat/ie_operation_detail.html', {
        **perms,
        'op': op,
        'groups': SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'machines': ie_machine_options(extra_code=op.machine_code),
        'skill_levels': ensure_skill_levels_abc(),
        'process_stages': ensure_process_stage_defaults(),
        'stitch_classes': SxStitchClass.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'smv_sources': SxSmvSource.objects.filter(is_active=True).order_by('sort_order', 'code'),
        'product_parts': product_parts,
        'smv_basis_choices': smv_basis_choices,
        'default_smv_basis': default_smv_basis_name(),
        'current_user_display_name': current_owner,
        'status_choices': [
            c for c in SxOperation.STATUS_CHOICES if c[0] != SxOperation.STATUS_APPROVED
        ],
        'audit_logs': SxIeAuditLog.objects.filter(
            object_type='SxOperation', object_id=str(op.pk)
        )[:20],
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_list(request):
    perms = _perm_ctx(request)
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        back = request.get_full_path() if request.GET else reverse('san_xuat:ie_routing_list')
        if action == 'import':
            return _handle_ie_import(request, redirect_to=back, kind=KIND_ROUTING)
        if action == 'create_routing':
            return _create_routing_from_post(request, fail_redirect='san_xuat:ie_routing_list')
        pk = (request.POST.get('pk') or '').strip()
        routing = SxRouting.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
        try:
            if action == 'update_routing' and routing:
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa routing.')
                update_routing_header(
                    routing=routing,
                    style_name=(request.POST.get('style_name') or '').strip(),
                    notes=(request.POST.get('notes') or '').strip(),
                    is_active=request.POST.get('is_active') == '1',
                )
                messages.success(request, f'Đã lưu routing {routing.routing_id}.')
            elif action == 'delete_routing' and routing:
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa routing.')
                rid = delete_routing(routing=routing)
                messages.success(request, f'Đã xóa routing {rid}.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect(back)

    qs = SxRouting.objects.annotate(
        n_lines=Count('lines'),
        sum_smv=Sum('lines__total_operation_smv'),
    )
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(routing_id__icontains=term)
            | Q(style_code__icontains=term)
            | Q(style_name__icontains=term)
        )
    qs = qs.order_by('style_code', 'routing_rev')
    page_obj, query_string = paginate_queryset(request, qs)
    from san_xuat.hub_models import SxProductionOrder
    locked_routing_ids = set(
        SxProductionOrder.objects.filter(routing_id__isnull=False).values_list('routing_id', flat=True)
    )
    grid = sx_list_grid_context(request, 'ie_routing')
    grid['sx_list_storage_key'] = 'san_xuat_ie_routing_cols_v4'
    return render(request, 'san_xuat/ie_routing_list.html', {
        **perms,
        **_ie_io_context(KIND_ROUTING),
        **grid,
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
        'locked_routing_ids': locked_routing_ids,
        'open_create': (request.GET.get('new') or '').strip() in ('1', 'true', 'yes'),
        'prefill_style_code': (request.GET.get('style_code') or '').strip(),
        'prefill_style_name': (request.GET.get('style_name') or '').strip(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def routing_detail(request, pk: int):
    routing = get_object_or_404(SxRouting, pk=pk)
    perms = _perm_ctx(request)
    locked = is_routing_locked(routing)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'approve_routing':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền duyệt routing (cần quyền Sửa menu Duyệt phát hành).')
                approve_routing(routing=routing, user=request.user)
                messages.success(request, f'Đã duyệt routing {routing.routing_id}.')
            elif action == 'reject_routing':
                if not perms['can_approve']:
                    raise IeOpsError('Bạn không có quyền từ chối routing (cần quyền Sửa menu Duyệt phát hành).')
                reject_routing(routing=routing, user=request.user)
                messages.success(request, f'Đã từ chối routing {routing.routing_id}.')
            elif action == 'clone_revision':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền tạo phiên bản routing.')
                clone = clone_routing_revision(routing=routing, user=request.user)
                messages.success(request, f'Đã tạo phiên bản mới {clone.routing_id}.')
                return redirect('san_xuat:ie_routing_detail', pk=clone.pk)
            elif action == 'save_explanations':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa giải trình.')
                explanations = {}
                for key, val in request.POST.items():
                    if key.startswith('expl_') and key[5:].isdigit():
                        explanations[int(key[5:])] = val
                n = save_routing_line_explanations(routing=routing, explanations=explanations)
                messages.success(request, f'Đã lưu {n} giải trình lệch SMV.')
            elif action in ('add_line', 'edit_line'):
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa dòng routing.')
                line_pk = request.POST.get('line_pk')
                line_pk = int(line_pk) if line_pk and str(line_pk).isdigit() else None
                seq_raw = (request.POST.get('seq_no') or '').strip()
                upsert_routing_line(
                    routing=routing,
                    line_pk=line_pk if action == 'edit_line' else None,
                    seq_no=int(seq_raw) if seq_raw.isdigit() else None,
                    op_code=(request.POST.get('op_code') or '').strip(),
                    op_rev=(request.POST.get('op_rev') or 'R01').strip(),
                    op_name_vi=(request.POST.get('op_name_vi') or '').strip(),
                    group_code=(request.POST.get('group_code') or '').strip(),
                    qty_per_garment=_dec(request.POST.get('qty_per_garment'), '1'),
                    applied_unit_smv=None,
                    library_unit_smv=_dec(request.POST.get('library_unit_smv'))
                    if (request.POST.get('library_unit_smv') or '').strip() != ''
                    else None,
                    machine_code=(request.POST.get('machine_code') or '').strip(),
                    work_center_code=(request.POST.get('work_center_code') or '').strip(),
                    skill_level_label=(request.POST.get('skill_level_label') or '').strip(),
                    price_factor=_dec(request.POST.get('price_factor'), '0'),
                    total_unit_price=_dec(request.POST.get('total_unit_price'), '0'),
                    variance_explanation=(request.POST.get('variance_explanation') or '').strip(),
                    notes=(request.POST.get('notes') or '').strip(),
                )
                messages.success(request, 'Đã lưu dòng routing.')
            elif action == 'delete_line':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa dòng routing.')
                line_pk = request.POST.get('line_pk')
                if not line_pk or not str(line_pk).isdigit():
                    raise IeOpsError('Thiếu dòng cần xóa.')
                delete_routing_line(routing=routing, line_pk=int(line_pk))
                messages.success(request, 'Đã xóa dòng routing.')
            elif action == 'save_header':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa routing.')
                update_routing_header(
                    routing=routing,
                    style_name=(request.POST.get('style_name') or '').strip(),
                    notes=(request.POST.get('notes') or '').strip(),
                )
                messages.success(request, f'Đã lưu routing {routing.routing_id}.')
            elif action == 'delete_routing':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền xóa routing.')
                rid = delete_routing(routing=routing)
                messages.success(request, f'Đã xóa routing {rid}.')
                return redirect('san_xuat:ie_routing_list')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return redirect('san_xuat:ie_routing_detail', pk=routing.pk)

    enrich_routing_lines_from_library(routing)
    lines = routing.lines.select_related(
        'operation', 'operation__group', 'operation__machine', 'machine', 'work_center',
    ).order_by('seq_no')
    high_var = [l for l in lines if abs(l.smv_variance_pct or 0) > 15]
    edit_line = None
    edit_pk = (request.GET.get('edit') or '').strip()
    if edit_pk.isdigit() and perms['can_update'] and not locked:
        edit_line = routing.lines.filter(pk=int(edit_pk)).first()
    from san_xuat.services.capacity_from_hrm import hr_work_centers_qs
    work_centers = list(hr_work_centers_qs())
    operation_groups = list(
        SxOperationGroup.objects.filter(is_active=True).order_by('sort_order', 'code')
    )
    if edit_line and (edit_line.group_code or '').strip():
        known = {g.code for g in operation_groups}
        gc = edit_line.group_code.strip()
        if gc not in known:
            operation_groups.insert(0, SxOperationGroup(code=gc, name=gc))
    last_seq = routing.lines.order_by('-seq_no').values_list('seq_no', flat=True).first() or 0
    default_seq_no = int(last_seq) + 1 if not edit_line else None
    return render(request, 'san_xuat/ie_routing_detail.html', {
        **perms,
        'routing': routing,
        'lines': lines,
        'total_smv': routing.total_smv,
        'locked': locked,
        'high_var_count': len(high_var),
        'edit_line': edit_line,
        'machines': ie_machine_options(extra_code=(edit_line.machine_code if edit_line else '')),
        'work_centers': work_centers,
        'skill_levels': ensure_skill_levels_abc(),
        'operation_groups': operation_groups,
        'default_seq_no': default_seq_no,
        'default_work_center_code': '',
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def ie_machine_search_api(request):
    """API tìm máy sản xuất — TomSelect form routing/thư viện."""
    q = (request.GET.get('q') or '').strip()
    return JsonResponse({'results': ie_machine_search(q=q, limit=60)})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def ie_operation_search(request):
    """API tìm công đoạn thư viện — mỗi kết quả là cặp OP_CODE + OP_REV (rule IE)."""
    q = (request.GET.get('q') or '').strip()
    qs = (
        SxOperation.objects.exclude(status=SxOperation.STATUS_RETIRED)
        .select_related('group__default_work_center', 'machine')
        .order_by('op_code', 'op_rev')
    )
    if q:
        qs = qs.filter(
            Q(op_code__icontains=q)
            | Q(name_vi__icontains=q)
            | Q(name_en__icontains=q)
        )
    results = []
    for op in qs[:60]:
        snap = operation_library_snapshot(op)
        results.append({
            'id': f'{op.op_code}|{op.op_rev}',
            'text': f'{op.op_code}/{op.op_rev} — {op.name_vi}',
            'op_code': op.op_code,
            'op_rev': op.op_rev,
            'name_vi': snap.get('name_vi', ''),
            'group_code': snap.get('group_code', ''),
            'machine_code': snap.get('machine_code', ''),
            'library_unit_smv': str(snap.get('library_smv') or '0'),
            'applied_unit_smv': str(snap.get('applied_unit_smv') or snap.get('library_smv') or '0'),
            'work_center_code': snap.get('work_center_code', ''),
            'skill_level_label': snap.get('skill_level_label', ''),
        })
    return JsonResponse({'results': results})


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def ie_operation_lookup(request):
    """API tra cứu công đoạn thư viện — điền form routing."""
    op_code = (request.GET.get('op_code') or '').strip()
    op_rev = (request.GET.get('op_rev') or 'R01').strip()
    if not op_code:
        return JsonResponse({'ok': False, 'error': 'Thiếu mã công đoạn.'}, status=400)
    op = resolve_operation(op_code, op_rev)
    if not op:
        return JsonResponse({'ok': False, 'error': f'Không tìm thấy {op_code}/{op_rev} trong thư viện.'}, status=404)
    op = (
        SxOperation.objects.select_related('group__default_work_center', 'machine')
        .filter(pk=op.pk)
        .first()
    )
    snap = operation_library_snapshot(op)
    return JsonResponse({
        'ok': True,
        'op_code': op.op_code,
        'op_rev': snap.get('op_rev', op.op_rev),
        'name_vi': snap.get('name_vi', ''),
        'group_code': snap.get('group_code', ''),
        'machine_code': snap.get('machine_code', ''),
        'library_unit_smv': str(snap.get('library_smv') or '0'),
        'applied_unit_smv': str(snap.get('applied_unit_smv') or snap.get('library_smv') or '0'),
        'work_center_code': snap.get('work_center_code', ''),
        'skill_level_label': snap.get('skill_level_label', ''),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def time_study_list(request):
    return redirect('san_xuat:ie_hub')


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_dashboard(request):
    import json

    data = build_ie_dashboard()
    return render(request, 'san_xuat/ie_dashboard.html', {
        **_perm_ctx(request),
        **data,
        'chart_style_labels_json': json.dumps(data['chart_style_labels'], ensure_ascii=False),
        'chart_total_smv_json': json.dumps(data['chart_total_smv']),
        'chart_sew_smv_json': json.dumps(data['chart_sew_smv']),
        'chart_other_smv_json': json.dumps(data['chart_other_smv']),
        'chart_op_status_json': json.dumps(data['chart_op_status']),
        'chart_routing_status_json': json.dumps(data['chart_routing_status']),
        'chart_ts_status_json': json.dumps(data['chart_ts_status']),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_audit_list(request):
    qs = SxIeAuditLog.objects.select_related('user').all()
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(
            Q(summary__icontains=term)
            | Q(object_repr__icontains=term)
            | Q(username__icontains=term)
            | Q(object_type__icontains=term)
        )
    action = (request.GET.get('action') or '').strip()
    if action:
        qs = qs.filter(action=action)
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_audit_list.html', {
        **_perm_ctx(request),
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'action': action,
        'action_choices': SxIeAuditLog.ACTION_CHOICES,
        'total': qs.count(),
    })


# --- Thiết lập công đoạn (catalog refs) ------------------------------------

IE_REF_CATALOGS = {
    'cum-chi-tiet': {
        'model': SxProductPart,
        'title': 'Cụm chi tiết',
        'code_label': 'Mã cụm',
        'name_label': 'Tên cụm chi tiết',
        'hint': 'Dùng cho cột Cụm chi tiết chính trên thư viện công đoạn.',
    },
    'bac-ky-nang': {
        'model': SxSkillLevel,
        'title': 'Bậc kỹ năng',
        'code_label': 'Mã bậc',
        'name_label': 'Tên bậc kỹ năng',
        'hint': 'Mặc định A / B / C — dùng trên công đoạn chuẩn và dòng routing.',
    },
    'khau-san-xuat': {
        'model': SxProcessStage,
        'title': 'Khâu sản xuất',
        'code_label': 'Mã khâu',
        'name_label': 'Tên khâu sản xuất',
        'hint': 'VD: Cắt, May lắp ráp, Hoàn thiện — dùng trên nhóm và công đoạn chuẩn.',
    },
    'lop-mui-may': {
        'model': SxStitchClass,
        'title': 'Lớp mũi may',
        'code_label': 'Mã lớp mũi',
        'name_label': 'Tên lớp mũi',
        'hint': 'VD: 301, 401, 504 — chọn trên công đoạn chuẩn.',
    },
    'nguon-smv': {
        'model': SxSmvSource,
        'title': 'Nguồn SMV',
        'code_label': 'Mã nguồn',
        'name_label': 'Tên nguồn SMV',
        'hint': 'VD: Time study, PMTS/GSD, Ước tính IE.',
    },
    'don-vi-smv': {
        'model': SxSmvBasis,
        'title': 'Đơn vị cơ sở SMV',
        'code_label': 'Mã đơn vị',
        'name_label': 'Tên đơn vị',
        'hint': 'VD: Phút/SP, Giây, SP/H — cột Đơn vị trên thư viện công đoạn.',
    },
}


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_settings_hub(request):
    denied = _require_ie_settings_access(request)
    if denied:
        return denied
    ensure_skill_levels_abc()
    ensure_process_stage_defaults()
    ensure_smv_basis_defaults()
    counts = {
        'product_parts': SxProductPart.objects.filter(is_active=True).count(),
        'skill_levels': SxSkillLevel.objects.filter(is_active=True).count(),
        'process_stages': SxProcessStage.objects.filter(is_active=True).count(),
        'stitch_classes': SxStitchClass.objects.filter(is_active=True).count(),
        'smv_sources': SxSmvSource.objects.filter(is_active=True).count(),
        'smv_bases': SxSmvBasis.objects.filter(is_active=True).count(),
        'approvers': ensure_ie_approver_group().user_set.count(),
    }
    return render(request, 'san_xuat/ie_settings_hub.html', {
        **_settings_perm_ctx(request),
        'counts': counts,
        'catalogs': IE_REF_CATALOGS,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_approve_hub(request):
    denied = _require_ie_approve_access(request)
    if denied:
        return denied

    perms = _approve_perm_ctx(request)
    kind = (request.GET.get('kind') or request.POST.get('kind') or IE_APPROVE_KIND_ALL).strip()
    if kind not in IE_APPROVE_KINDS:
        kind = IE_APPROVE_KIND_ALL
    status = (request.GET.get('status') or request.POST.get('status') or IE_APPROVE_STATUS_PENDING).strip()
    if status not in IE_APPROVE_STATUSES:
        status = IE_APPROVE_STATUS_PENDING
    term = (request.GET.get('q') or request.POST.get('q') or '').strip()
    back = _ie_approve_hub_url(kind=kind, term=term, status=status)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        raw_pks = request.POST.getlist('pk')

        def _redirect_with_messages():
            return redirect(back)

        try:
            if action in ('bulk_approve', 'bulk_reject') and raw_pks:
                op_pks, rt_pks = _parse_approve_pks(raw_pks, kind=kind)
                if op_pks or rt_pks:
                    _bulk_approve_reject(
                        request=request,
                        action=action,
                        op_pks=op_pks,
                        routing_pks=rt_pks,
                        perms=perms,
                    )
            elif action == 'approve_operation':
                pk = (request.POST.get('pk') or '').strip()
                op = SxOperation.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
                if op:
                    if not perms['can_approve']:
                        raise IeOpsError('Bạn không có quyền duyệt (cần quyền Sửa menu Duyệt phát hành).')
                    approve_operation(operation=op, user=request.user)
                    messages.success(request, f'Đã duyệt {op.op_code}/{op.op_rev}.')
                else:
                    messages.error(request, 'Hành động không hợp lệ.')
            elif action in ('approve_routing', 'reject_routing'):
                pk = (request.POST.get('pk') or '').strip()
                routing = SxRouting.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
                if routing:
                    if not perms['can_approve']:
                        raise IeOpsError('Bạn không có quyền duyệt routing (cần quyền Sửa menu Duyệt phát hành).')
                    if action == 'approve_routing':
                        if routing.pk in _locked_routing_ids():
                            raise IeOpsError(f'Routing {routing.routing_id} đã khóa — tạo REV mới.')
                        approve_routing(routing=routing, user=request.user)
                        messages.success(request, f'Đã duyệt phát hành {routing.routing_id}.')
                    else:
                        reject_routing(routing=routing, user=request.user)
                        messages.success(request, f'Đã từ chối {routing.routing_id}.')
                else:
                    messages.error(request, 'Hành động không hợp lệ.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        return _redirect_with_messages()

    pending_ops = _pending_operations_qs().count()
    pending_routings = _pending_routings_qs().count()
    locked_routing_ids = _locked_routing_ids()
    show_bulk_actions = status == IE_APPROVE_STATUS_PENDING

    if kind == IE_APPROVE_KIND_ALL:
        op_items = list(_filter_operations_for_approval(term, status))
        routing_items = list(_filter_routings_for_approval(term, status))
        all_rows = _build_approve_rows(
            operations=op_items,
            routings=routing_items,
            locked_ids=locked_routing_ids,
        )
        page_obj, query_string = paginate_queryset(request, all_rows)
        ctx = {
            **perms,
            'kind': kind,
            'kind_all': IE_APPROVE_KIND_ALL,
            'kind_operation': IE_APPROVE_KIND_OPERATION,
            'kind_routing': IE_APPROVE_KIND_ROUTING,
            'status': status,
            'status_pending': IE_APPROVE_STATUS_PENDING,
            'status_choices': IE_APPROVE_STATUS_CHOICES,
            'page_obj': page_obj,
            'approve_rows': page_obj.object_list,
            'query_string': query_string,
            'term': term,
            'total': len(all_rows),
            'pending_ops': pending_ops,
            'pending_routings': pending_routings,
            'locked_routing_ids': locked_routing_ids,
            'show_bulk_actions': show_bulk_actions,
            'has_active_filters': bool(term) or kind != IE_APPROVE_KIND_ALL or status != IE_APPROVE_STATUS_PENDING,
        }
        return render(request, 'san_xuat/ie_approve_hub.html', ctx)

    if kind == IE_APPROVE_KIND_OPERATION:
        qs = _filter_operations_for_approval(term, status)
    else:
        qs = _filter_routings_for_approval(term, status)

    page_obj, query_string = paginate_queryset(request, qs)
    items = page_obj.object_list
    if kind == IE_APPROVE_KIND_OPERATION:
        approve_rows = _build_approve_rows(operations=items, locked_ids=locked_routing_ids)
    else:
        approve_rows = _build_approve_rows(routings=items, locked_ids=locked_routing_ids)
    ctx = {
        **perms,
        'kind': kind,
        'kind_all': IE_APPROVE_KIND_ALL,
        'kind_operation': IE_APPROVE_KIND_OPERATION,
        'kind_routing': IE_APPROVE_KIND_ROUTING,
        'status': status,
        'status_pending': IE_APPROVE_STATUS_PENDING,
        'status_choices': IE_APPROVE_STATUS_CHOICES,
        'page_obj': page_obj,
        'approve_rows': approve_rows,
        'query_string': query_string,
        'term': term,
        'total': qs.count(),
        'pending_ops': pending_ops,
        'pending_routings': pending_routings,
        'locked_routing_ids': locked_routing_ids,
        'show_bulk_actions': show_bulk_actions,
        'has_active_filters': bool(term) or kind != IE_APPROVE_KIND_ALL or status != IE_APPROVE_STATUS_PENDING,
    }
    return render(request, 'san_xuat/ie_approve_hub.html', ctx)


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_approve_operations(request):
    params = {'kind': IE_APPROVE_KIND_OPERATION}
    term = (request.GET.get('q') or '').strip()
    if term:
        params['q'] = term
    return redirect(f"{reverse('san_xuat:ie_approve_hub')}?{urlencode(params)}")


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_approve_routing(request):
    params = {'kind': IE_APPROVE_KIND_ROUTING}
    term = (request.GET.get('q') or '').strip()
    if term:
        params['q'] = term
    return redirect(f"{reverse('san_xuat:ie_approve_hub')}?{urlencode(params)}")


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_ref_catalog(request, kind: str):
    denied = _require_ie_settings_access(request)
    if denied:
        return denied
    meta = IE_REF_CATALOGS.get(kind)
    if not meta:
        messages.error(request, 'Danh mục không hợp lệ.')
        return redirect('san_xuat:ie_settings_hub')
    if kind == 'bac-ky-nang':
        ensure_skill_levels_abc()
    elif kind == 'khau-san-xuat':
        ensure_process_stage_defaults()
    elif kind == 'don-vi-smv':
        ensure_smv_basis_defaults()
    Model = meta['model']
    perms = _settings_perm_ctx(request)
    list_url = reverse('san_xuat:ie_ref_catalog', kwargs={'kind': kind})

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action == 'create_ref':
                if not (perms['can_create'] or perms['can_update']):
                    raise IeOpsError('Bạn không có quyền thêm danh mục.')
                code = (request.POST.get('code') or '').strip()[:40]
                if kind in ('bac-ky-nang', 'don-vi-smv', 'khau-san-xuat'):
                    code = code.upper()
                name = (request.POST.get('name') or '').strip()[:150] or code
                if not code:
                    raise IeOpsError('Nhập mã.')
                sort_raw = (request.POST.get('sort_order') or '').strip()
                sort_order = int(sort_raw) if sort_raw.isdigit() else 100
                notes = (request.POST.get('notes') or '').strip()[:255]
                obj, created = Model.objects.update_or_create(
                    code=code,
                    defaults={
                        'name': name,
                        'sort_order': sort_order,
                        'is_active': request.POST.get('is_active') == '1',
                        'notes': notes,
                    },
                )
                messages.success(request, f'{"Đã thêm" if created else "Đã cập nhật"} {obj.code}.')
            elif action == 'update_ref':
                if not perms['can_update']:
                    raise IeOpsError('Bạn không có quyền sửa danh mục.')
                pk = (request.POST.get('pk') or '').strip()
                obj = Model.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
                if not obj:
                    raise IeOpsError('Không tìm thấy bản ghi.')
                name = (request.POST.get('name') or '').strip()[:150]
                if name:
                    obj.name = name
                sort_raw = (request.POST.get('sort_order') or '').strip()
                if sort_raw.isdigit():
                    obj.sort_order = int(sort_raw)
                obj.is_active = request.POST.get('is_active') == '1'
                obj.notes = (request.POST.get('notes') or '').strip()[:255]
                obj.save()
                messages.success(request, f'Đã lưu {obj.code}.')
            elif action == 'delete_ref':
                if not (perms['can_delete'] or perms['can_update']):
                    raise IeOpsError('Bạn không có quyền xóa danh mục.')
                pk = (request.POST.get('pk') or '').strip()
                obj = Model.objects.filter(pk=int(pk)).first() if pk.isdigit() else None
                if not obj:
                    raise IeOpsError('Không tìm thấy bản ghi.')
                code = obj.code
                obj.delete()
                messages.success(request, f'Đã xóa {code}.')
            elif action == 'import':
                return _handle_ref_catalog_import(request, kind=kind, redirect_to=list_url)
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except IeOpsError as exc:
            messages.error(request, str(exc))
        except Exception as exc:  # unique constraint, etc.
            messages.error(request, str(exc))
        return redirect(list_url)

    qs = Model.objects.all().order_by('sort_order', 'code')
    term = (request.GET.get('q') or '').strip()
    if term:
        qs = qs.filter(Q(code__icontains=term) | Q(name__icontains=term) | Q(notes__icontains=term))
    active_filter = (request.GET.get('active') or '').strip()
    if active_filter == '1':
        qs = qs.filter(is_active=True)
    elif active_filter == '0':
        qs = qs.filter(is_active=False)
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'san_xuat/ie_ref_catalog.html', {
        **perms,
        **_ref_io_context(kind),
        'kind': kind,
        'meta': meta,
        'page_obj': page_obj,
        'items': page_obj.object_list,
        'query_string': query_string,
        'term': term,
        'active_filter': active_filter,
        'total': qs.count(),
    })


@module_perm_required(MODULE_SAN_XUAT, 'export')
@require_GET
def ie_ref_catalog_export(request, kind: str):
    denied = _require_ie_settings_access(request)
    if denied:
        return denied
    if not user_can_export_menu(request.user, MODULE_SAN_XUAT, IE_SETTINGS_MENU_KEY):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, IE_SETTINGS_MENU_KEY)
    try:
        return export_ref_catalog_response(kind, template=False, user=request.user)
    except RefCatalogImportError as exc:
        messages.error(request, str(exc))
        return redirect('san_xuat:ie_settings_hub')


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_GET
def ie_ref_catalog_import_template(request, kind: str):
    denied = _require_ie_settings_access(request)
    if denied:
        return denied
    try:
        return export_ref_catalog_response(kind, template=True)
    except RefCatalogImportError as exc:
        messages.error(request, str(exc))
        return redirect('san_xuat:ie_settings_hub')


def _require_ie_settings_access(request):
    from hrm.menu_permissions import user_can_access_menu

    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, IE_SETTINGS_MENU_KEY):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, IE_SETTINGS_MENU_KEY)
    return None


@module_perm_required(MODULE_SAN_XUAT, 'view')
def ie_approver_manage(request):
    """Quản lý danh sách người duyệt IE (nhóm SX_IE_Approver)."""
    denied = _require_ie_settings_access(request)
    if denied:
        return denied

    from san_xuat.ie_permissions import (
        IE_APPROVER_GROUP,
        add_ie_approver_by_username,
        ie_approver_group_has_members,
        list_ie_approver_candidates,
        list_ie_approvers,
        remove_ie_approver_by_username,
    )

    perms = _settings_perm_ctx(request)
    list_url = reverse('san_xuat:ie_approver_manage')

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        username = (request.POST.get('username') or '').strip()
        if not perms['can_update']:
            messages.error(request, 'Bạn không có quyền cập nhật người duyệt.')
            return redirect(list_url)
        try:
            if action == 'add_ie_approver':
                user, created = add_ie_approver_by_username(username)
                if created:
                    messages.success(request, f'Đã thêm {user.username} vào nhóm {IE_APPROVER_GROUP}.')
                else:
                    messages.info(request, f'{user.username} đã là người duyệt.')
            elif action == 'remove_ie_approver':
                user = remove_ie_approver_by_username(username)
                messages.success(request, f'Đã gỡ {user.username} khỏi nhóm {IE_APPROVER_GROUP}.')
            else:
                messages.error(request, 'Hành động không hợp lệ.')
        except ValueError as exc:
            messages.error(request, str(exc))
        return redirect(list_url)

    return render(request, 'san_xuat/ie_approver_manage.html', {
        **perms,
        'ie_approver_group_name': IE_APPROVER_GROUP,
        'ie_approver_ready': ie_approver_group_has_members(),
        'ie_approvers': list_ie_approvers(),
        'ie_candidate_users': list_ie_approver_candidates(),
    })
