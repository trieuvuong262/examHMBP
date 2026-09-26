"""Duyệt giá NPL — hàng chờ Sếp + bảng so giá KHSX."""

from __future__ import annotations

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from assessment.decorators import module_perm_required
from hrm.menu_permissions import (
    handle_menu_access_denied,
    user_can_access_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_SAN_XUAT
from kho_npl.models import Supplier
from san_xuat.hub_models import SxNplPurchaseRequest, SxNplQuoteSheet, SxSalesOrder
from san_xuat.services.planning import PlanningError
from san_xuat.services.price_approval import (
    approve_price_review,
    create_quote_sheet,
    decide_quote_sheet,
    quote_sheet_groups,
    return_price_review,
    return_quote_sheet,
    save_quote_offers,
    sheet_has_three_suppliers,
    submit_quote_sheet,
)

MENU_APPROVE = 'sx_price_approve'
MENU_QUOTE = 'sx_price_quote'


def _guard_approve(request):
    if user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_APPROVE):
        return None
    return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU_APPROVE)


def _guard_quote(request):
    """KHSX so giá hoặc Sếp (để mở bảng từ hàng chờ)."""
    if user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE):
        return None
    if user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_APPROVE):
        return None
    return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU_QUOTE)


def _can_decide(request) -> bool:
    return user_can_update_menu(request.user, MODULE_SAN_XUAT, MENU_APPROVE)


def _can_edit_quote(request) -> bool:
    return (
        user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE)
        or user_can_update_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE)
    )


def _offer_rows(post):
    indexes = []
    for key in post:
        if key.startswith('mat__') or key.startswith('mid__'):
            indexes.append(key.split('__', 1)[1])
    seen = set()
    ordered = []
    for idx in indexes:
        if idx not in seen:
            seen.add(idx)
            ordered.append(idx)
    rows = []
    for idx in ordered:
        rows.append({
            'material_id': post.get(f'mid__{idx}'),
            'material_code': post.get(f'mat__{idx}'),
            'material_name': post.get(f'name__{idx}'),
            'supplier_id': post.get(f'sup__{idx}'),
            'unit_price': post.get(f'price__{idx}'),
            'quality_note': post.get(f'quality__{idx}'),
            'capacity_note': post.get(f'capacity__{idx}'),
        })
    return rows


def _chosen_ids(post) -> list[int]:
    ids: list[int] = []
    for key, value in post.items():
        if key == 'chosen' or key.startswith('chosen__'):
            try:
                rid = int(value)
            except (TypeError, ValueError):
                continue
            if rid and rid not in ids:
                ids.append(rid)
    for value in post.getlist('chosen'):
        try:
            rid = int(value)
        except (TypeError, ValueError):
            continue
        if rid and rid not in ids:
            ids.append(rid)
    return ids


@module_perm_required(MODULE_SAN_XUAT, 'view')
def price_material_search(request):
    denied = _guard_quote(request)
    if denied:
        return denied
    from django.http import JsonResponse
    from kho_npl.catalog_labels import color_label, spec_label, unit_label
    from kho_npl.material_search import apply_material_search_strict, material_relevance_sort_key
    from kho_npl.models import Material

    q = (request.GET.get('q') or '').strip()
    try:
        limit = min(max(int(request.GET.get('limit') or 40), 1), 100)
    except (TypeError, ValueError):
        limit = 40
    qs = (
        Material.objects.filter(is_active=True)
        .select_related('unit', 'color', 'specification', 'category')
        .order_by('name', 'code')
    )
    if q:
        qs = apply_material_search_strict(qs, q)
        materials = sorted(qs[:200], key=lambda m: material_relevance_sort_key(m, q))[:limit]
    else:
        materials = list(qs[:limit])
    rows = []
    for material in materials:
        image_url = ''
        if material.image:
            try:
                image_url = material.image.url or ''
            except ValueError:
                image_url = ''
        spec = spec_label(material.specification) if material.specification_id else ''
        color = color_label(material.color) if material.color_id else ''
        rows.append({
            'id': material.pk,
            'text': f'{material.code} — {material.name}',
            'code': material.code,
            'name': material.name,
            'unit': unit_label(material.unit) if material.unit_id else '',
            'unit_name': material.unit.name if material.unit_id else '',
            'specification': spec,
            'specification_name': material.specification.name if material.specification_id else '',
            'color': color,
            'variant_group': material.variant_group or '',
            'image_url': image_url,
            'base_price': float(material.base_price or 0),
        })
    return JsonResponse({'results': rows})


@module_perm_required(MODULE_SAN_XUAT, 'view')
def price_home(request):
    """Hàng chờ Sếp: chốt bảng so giá + duyệt giá đơn đặt."""
    if not user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_APPROVE):
        # KHSX vào URL cũ /duyet-gia/ → đưa sang bảng so giá, không đá về trang chủ.
        if user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE):
            return redirect('san_xuat:price_quote_list')
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU_APPROVE)
    waiting_quotes = list(
        SxNplQuoteSheet.objects.filter(
            is_demo=False,
            status=SxNplQuoteSheet.STATUS_SUBMITTED,
        )
        .select_related('sales_order', 'created_by')
        .prefetch_related('offers__material')
        .order_by('-created_at')[:80]
    )
    waiting = (
        SxNplPurchaseRequest.objects.filter(
            is_demo=False,
            status=SxNplPurchaseRequest.STATUS_PRICE_REVIEW,
        )
        .select_related('sales_order')
        .prefetch_related('lines__supplier')
        .order_by('-created_at')
    )
    return render(request, 'san_xuat/price_approve_home.html', {
        'waiting': waiting,
        'waiting_quotes': waiting_quotes,
        'can_decide': _can_decide(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
def price_quote_list(request):
    """Danh sách bảng so giá — KHSX."""
    denied = _guard_quote(request)
    if denied:
        return denied
    sheets = (
        SxNplQuoteSheet.objects.filter(is_demo=False)
        .select_related('sales_order', 'decided_by', 'created_by')
        .prefetch_related('offers')
        .order_by('-created_at')[:120]
    )
    return render(request, 'san_xuat/price_quote_list.html', {
        'sheets': sheets,
        'can_create': _can_edit_quote(request),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_http_methods(['GET', 'POST'])
def price_quote_create(request):
    denied = _guard_quote(request)
    if denied:
        return denied
    if not _can_edit_quote(request) and not user_can_access_menu(
        request.user, MODULE_SAN_XUAT, MENU_QUOTE,
    ):
        return handle_menu_access_denied(request, MODULE_SAN_XUAT, MENU_QUOTE)
    if request.method == 'POST':
        raw = (request.POST.get('sales_order') or '').strip()
        order_id = int(raw) if raw.isdigit() else None
        sheet = create_quote_sheet(
            title=request.POST.get('title') or '',
            sales_order_id=order_id,
            user=request.user,
        )
        notes = (request.POST.get('notes') or '').strip()
        if notes:
            sheet.notes = notes
            sheet.save(update_fields=['notes'])
        return redirect('san_xuat:price_quote_detail', pk=sheet.pk)
    orders = SxSalesOrder.objects.filter(is_demo=False).order_by('-id')[:80]
    return render(request, 'san_xuat/price_quote_create.html', {
        'orders': orders,
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_http_methods(['GET', 'POST'])
def price_quote_detail(request, pk: int):
    denied = _guard_quote(request)
    if denied:
        return denied
    sheet = get_object_or_404(
        SxNplQuoteSheet.objects.select_related('sales_order', 'decided_by', 'created_by')
        .prefetch_related(
            'offers__supplier',
            'offers__material',
            'offers__material__specification',
            'offers__material__color',
            'offers__material__unit',
        ),
        pk=pk,
        is_demo=False,
    )
    staff_edit = (
        sheet.status == SxNplQuoteSheet.STATUS_DRAFT
        and user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE)
    )
    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()
        try:
            if action in ('save', 'submit'):
                if not staff_edit:
                    raise PlanningError('Không có quyền sửa bảng so giá.')
                save_quote_offers(
                    sheet_id=sheet.pk,
                    rows=_offer_rows(request.POST),
                    user=request.user,
                    notes=request.POST.get('notes'),
                    title=request.POST.get('title'),
                )
                if action == 'submit':
                    submit_quote_sheet(sheet_id=sheet.pk)
                    messages.success(request, f'{sheet.code} đã gửi Sếp chốt giá.')
                else:
                    messages.success(request, f'Đã lưu bảng so giá {sheet.code}.')
            elif action == 'return_draft':
                if not (
                    user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE)
                    or _can_decide(request)
                ):
                    raise PlanningError('Không có quyền trả bảng về nháp.')
                return_quote_sheet(sheet_id=sheet.pk)
                messages.success(request, f'{sheet.code} đã trả về nháp.')
            elif action == 'decide':
                if not _can_decide(request):
                    messages.error(request, 'Không có quyền chốt giá.')
                    return redirect('san_xuat:price_quote_detail', pk=sheet.pk)
                decide_quote_sheet(
                    sheet_id=sheet.pk,
                    chosen_ids=_chosen_ids(request.POST),
                    user=request.user,
                )
                messages.success(
                    request,
                    f'Đã chốt giá {sheet.code}. NV lên đơn chọn đúng NCC+giá đã chốt.',
                )
            else:
                raise PlanningError('Thao tác không hợp lệ.')
        except PlanningError as exc:
            messages.error(request, str(exc))
        return redirect('san_xuat:price_quote_detail', pk=sheet.pk)

    groups = quote_sheet_groups(sheet)
    rule_ok = sheet_has_three_suppliers(sheet)
    return render(request, 'san_xuat/price_quote_detail.html', {
        'sheet': sheet,
        'groups': groups,
        'rule_ok': rule_ok,
        'suppliers': list(Supplier.objects.filter(is_active=True).order_by('name')),
        'can_decide': _can_decide(request),
        'can_edit': staff_edit,
        'can_return': (
            sheet.status == SxNplQuoteSheet.STATUS_SUBMITTED
            and (
                user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_QUOTE)
                or _can_decide(request)
            )
        ),
        'is_waiting': sheet.status == SxNplQuoteSheet.STATUS_SUBMITTED,
        'is_decided': sheet.status == SxNplQuoteSheet.STATUS_DECIDED,
        'approve_home': user_can_access_menu(request.user, MODULE_SAN_XUAT, MENU_APPROVE),
    })


@module_perm_required(MODULE_SAN_XUAT, 'view')
@require_http_methods(['POST'])
def price_review_action(request, pk: int):
    denied = _guard_approve(request)
    if denied:
        return denied
    if not _can_decide(request):
        messages.error(request, 'Không có quyền duyệt giá.')
        return redirect('san_xuat:price_approve_home')
    action = (request.POST.get('action') or '').strip()
    try:
        if action == 'approve':
            pr = approve_price_review(request_id=pk, user=request.user)
            messages.success(request, f'{pr.code} đã duyệt giá. Đơn sang Xác nhận đơn đặt hàng.')
        elif action == 'return':
            pr = return_price_review(request_id=pk, note=request.POST.get('note') or '')
            messages.success(request, f'{pr.code} đã trả về nháp.')
        else:
            raise PlanningError('Thao tác không hợp lệ.')
    except PlanningError as exc:
        messages.error(request, str(exc))
    return redirect('san_xuat:price_approve_home')
