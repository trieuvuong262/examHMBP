"""Bảng so giá NPL và duyệt giá đơn đặt hàng."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from kho_npl.models import Material, Supplier
from san_xuat.hub_models import (
    SxNplPurchaseRequest,
    SxNplQuoteOffer,
    SxNplQuoteSheet,
    SxSalesOrder,
)
from san_xuat.services.planning import PlanningError, _code


def _q(value) -> Decimal:
    try:
        return Decimal(str(value or '0'))
    except Exception:
        return Decimal('0')


def _resolve_material(*, material_id=None, material_code: str = '') -> Material:
    mid = 0
    try:
        mid = int(material_id or 0)
    except (TypeError, ValueError):
        mid = 0
    code = (material_code or '').strip()
    mat = None
    if mid:
        mat = Material.objects.filter(pk=mid, is_active=True).first()
    if mat is None and code:
        mat = Material.objects.filter(code__iexact=code, is_active=True).first()
    if mat is None:
        label = code or (f'#{mid}' if mid else '')
        raise PlanningError(
            f'NPL không có trong kho hoặc đã ngưng: {label or "—"}. '
            'Chọn từ danh mục kho NPL.'
        )
    return mat


def chosen_offers():
    return (
        SxNplQuoteOffer.objects.filter(
            is_chosen=True,
            sheet__status=SxNplQuoteSheet.STATUS_DECIDED,
            sheet__is_demo=False,
        )
        .select_related('supplier', 'sheet')
        .order_by('material_code', 'id')
    )


def chosen_offers_for_code(material_code: str):
    code = (material_code or '').strip()
    if not code:
        return SxNplQuoteOffer.objects.none()
    return chosen_offers().filter(material_code__iexact=code)


@transaction.atomic
def create_quote_sheet(*, title: str = '', sales_order_id: int | None = None, user=None) -> SxNplQuoteSheet:
    order = None
    if sales_order_id:
        order = SxSalesOrder.objects.filter(pk=sales_order_id, is_demo=False).first()
    return SxNplQuoteSheet.objects.create(
        code=_code('npl_quote', SxNplQuoteSheet),
        title=(title or '').strip()[:200],
        sales_order=order,
        status=SxNplQuoteSheet.STATUS_DRAFT,
        is_demo=False,
        created_by=user if getattr(user, 'pk', None) else None,
    )


def _offers_by_material(sheet: SxNplQuoteSheet) -> dict[str, list[SxNplQuoteOffer]]:
    buckets: dict[str, list[SxNplQuoteOffer]] = defaultdict(list)
    offers = sheet.offers.select_related(
        'supplier', 'material', 'material__specification', 'material__color', 'material__unit',
    )
    for offer in offers:
        buckets[(offer.material_code or '').strip().casefold()].append(offer)
    return buckets


def sheet_has_three_suppliers(sheet: SxNplQuoteSheet) -> bool:
    for offers in _offers_by_material(sheet).values():
        suppliers = {o.supplier_id for o in offers if o.supplier_id}
        if len(suppliers) >= 3:
            return True
    return False


def quote_sheet_groups(sheet: SxNplQuoteSheet) -> list[dict]:
    """Nhóm báo giá theo mã NPL kèm kiểm rule (≥3 NCC, giá thấp nhất)."""
    from kho_npl.catalog_labels import color_label, spec_label, unit_label

    buckets = _offers_by_material(sheet)
    groups: list[dict] = []
    for key in sorted(buckets.keys()):
        offers = sorted(buckets[key], key=lambda o: (_q(o.unit_price), o.pk))
        suppliers = {o.supplier_id for o in offers if o.supplier_id}
        supplier_count = len(suppliers)
        prices = [_q(o.unit_price) for o in offers if _q(o.unit_price) > 0]
        min_price = min(prices) if prices else None
        sample = offers[0]
        mat = sample.material
        groups.append({
            'material_code': sample.material_code,
            'material_name': sample.material_name or sample.material_code,
            'material_id': sample.material_id,
            'material': mat,
            'specification': spec_label(mat.specification) if mat and mat.specification_id else '',
            'color': color_label(mat.color) if mat and mat.color_id else '',
            'unit': unit_label(mat.unit) if mat and mat.unit_id else '',
            'offers': offers,
            'supplier_count': supplier_count,
            'meets_rule': supplier_count >= 3,
            'min_price': min_price,
            'chosen': next((o for o in offers if o.is_chosen), None),
        })
    return groups


def _assert_offer_complete(offer: SxNplQuoteOffer):
    code = offer.material_code or 'NPL'
    if _q(offer.unit_price) <= 0:
        raise PlanningError(f'{code} · {offer.supplier}: đơn giá phải lớn hơn 0.')
    if not (offer.quality_note or '').strip():
        raise PlanningError(f'{code} · {offer.supplier}: nhập ghi chú chất lượng.')
    if not (offer.capacity_note or '').strip():
        raise PlanningError(f'{code} · {offer.supplier}: nhập ghi chú năng lực.')


@transaction.atomic
def save_quote_offers(
    *,
    sheet_id: int,
    rows: list[dict],
    user=None,
    notes: str | None = None,
    title: str | None = None,
) -> SxNplQuoteSheet:
    sheet = SxNplQuoteSheet.objects.select_for_update().get(pk=sheet_id, is_demo=False)
    if sheet.status == SxNplQuoteSheet.STATUS_DECIDED:
        raise PlanningError('Bảng đã chốt giá — không sửa báo giá.')
    if sheet.status == SxNplQuoteSheet.STATUS_SUBMITTED:
        raise PlanningError('Bảng đang chờ chốt — trả về nháp trước khi sửa.')
    seen_pairs: set[tuple[str, int]] = set()
    kept: list[int] = []
    for row in rows:
        try:
            supplier_id = int(row.get('supplier_id') or 0)
        except (TypeError, ValueError):
            supplier_id = 0
        if not supplier_id:
            continue
        # Cho phép bỏ qua dòng trống (chưa chọn NPL)
        raw_mid = row.get('material_id')
        raw_code = (row.get('material_code') or '').strip()
        if not raw_mid and not raw_code:
            continue
        material = _resolve_material(material_id=raw_mid, material_code=raw_code)
        code = material.code
        name = material.name
        pair = (code.casefold(), supplier_id)
        if pair in seen_pairs:
            raise PlanningError(f'{code}: trùng nhà cung cấp trong cùng một NPL.')
        seen_pairs.add(pair)
        supplier = Supplier.objects.filter(pk=supplier_id, is_active=True).first()
        if supplier is None:
            raise PlanningError(f'Nhà cung cấp không còn dùng cho mã {code}.')
        price = _q(row.get('unit_price'))
        if price < 0:
            raise PlanningError('Đơn giá không được âm.')
        offer = SxNplQuoteOffer.objects.filter(
            sheet=sheet, material_code__iexact=code, supplier=supplier,
        ).first()
        fields = {
            'material': material,
            'material_code': code,
            'material_name': name,
            'unit_price': price,
            'quality_note': (row.get('quality_note') or '').strip()[:255],
            'capacity_note': (row.get('capacity_note') or '').strip()[:255],
            'is_chosen': False,
        }
        if offer is None:
            offer = SxNplQuoteOffer.objects.create(sheet=sheet, supplier=supplier, **fields)
        else:
            for key, value in fields.items():
                setattr(offer, key, value)
            offer.save(update_fields=list(fields))
        kept.append(offer.pk)
    sheet.offers.exclude(pk__in=kept).delete()
    update_fields = ['status']
    sheet.status = SxNplQuoteSheet.STATUS_DRAFT
    if notes is not None:
        sheet.notes = (notes or '').strip()
        update_fields.append('notes')
    if title is not None:
        sheet.title = (title or '').strip()[:200]
        update_fields.append('title')
    sheet.save(update_fields=update_fields)
    return sheet


@transaction.atomic
def submit_quote_sheet(*, sheet_id: int) -> SxNplQuoteSheet:
    sheet = SxNplQuoteSheet.objects.select_for_update().prefetch_related('offers__supplier').get(
        pk=sheet_id, is_demo=False,
    )
    if sheet.status == SxNplQuoteSheet.STATUS_DECIDED:
        raise PlanningError('Bảng đã chốt giá.')
    if sheet.status == SxNplQuoteSheet.STATUS_SUBMITTED:
        raise PlanningError('Bảng đã gửi chờ chốt giá.')
    offers = list(sheet.offers.all())
    if not offers:
        raise PlanningError('Nhập ít nhất một báo giá.')
    for offer in offers:
        _assert_offer_complete(offer)
    if not sheet_has_three_suppliers(sheet):
        raise PlanningError(
            'Rule so giá: ít nhất một NPL phải có báo giá từ 3 nhà cung cấp trở lên '
            '(để so giá / chất lượng / năng lực).'
        )
    sheet.status = SxNplQuoteSheet.STATUS_SUBMITTED
    sheet.save(update_fields=['status'])
    return sheet


@transaction.atomic
def return_quote_sheet(*, sheet_id: int) -> SxNplQuoteSheet:
    """Trả bảng chờ chốt về nháp để KHSX sửa lại."""
    sheet = SxNplQuoteSheet.objects.select_for_update().get(pk=sheet_id, is_demo=False)
    if sheet.status != SxNplQuoteSheet.STATUS_SUBMITTED:
        raise PlanningError('Chỉ trả về nháp khi bảng đang chờ chốt giá.')
    sheet.offers.filter(is_chosen=True).update(is_chosen=False)
    sheet.status = SxNplQuoteSheet.STATUS_DRAFT
    sheet.decided_by = None
    sheet.decided_at = None
    sheet.save(update_fields=['status', 'decided_by', 'decided_at'])
    return sheet


@transaction.atomic
def decide_quote_sheet(*, sheet_id: int, chosen_ids: list[int], user=None) -> SxNplQuoteSheet:
    sheet = SxNplQuoteSheet.objects.select_for_update().prefetch_related('offers__supplier').get(
        pk=sheet_id, is_demo=False,
    )
    if sheet.status != SxNplQuoteSheet.STATUS_SUBMITTED:
        raise PlanningError('Chỉ chốt khi bảng đang chờ chốt giá.')
    if not sheet_has_three_suppliers(sheet):
        raise PlanningError('Ít nhất một NPL phải có báo giá từ 3 nhà cung cấp trở lên.')
    ids = []
    for raw in chosen_ids or []:
        try:
            rid = int(raw)
        except (TypeError, ValueError):
            continue
        if rid and rid not in ids:
            ids.append(rid)
    offers = list(sheet.offers.all())
    chosen = [o for o in offers if o.pk in ids]
    if not chosen:
        raise PlanningError('Chọn một nhà cung cấp và giá cho mỗi mã NPL trên bảng.')
    by_mat: dict[str, int] = {}
    for offer in chosen:
        key = (offer.material_code or '').strip().casefold()
        if key in by_mat:
            raise PlanningError(
                f'Mỗi NPL chỉ chốt một nhà cung cấp. {offer.material_code} đang chọn hai.'
            )
        by_mat[key] = offer.pk
    all_mats = {(o.material_code or '').strip().casefold() for o in offers if o.material_code}
    missing = [code for code in all_mats if code not in by_mat]
    if missing:
        labels = sorted({
            (o.material_code or '').strip()
            for o in offers
            if (o.material_code or '').strip().casefold() in missing
        })
        raise PlanningError(
            'Sếp phải chọn đủ một NCC+giá cho mỗi NPL: ' + ', '.join(labels)
        )
    for offer in offers:
        offer.is_chosen = offer.pk in by_mat.values()
        offer.save(update_fields=['is_chosen'])
    sheet.status = SxNplQuoteSheet.STATUS_DECIDED
    sheet.decided_by = user if getattr(user, 'pk', None) else None
    sheet.decided_at = timezone.now()
    sheet.save(update_fields=['status', 'decided_by', 'decided_at'])
    return sheet


def assert_line_uses_chosen_quote(*, material_code: str, offer: SxNplQuoteOffer | None):
    if offer is None:
        raise PlanningError(
            f'{material_code}: chọn giá sếp đã chốt. Chưa có báo giá được chọn cho mã này.'
        )
    if not offer.is_chosen or offer.sheet.status != SxNplQuoteSheet.STATUS_DECIDED:
        raise PlanningError(f'{material_code}: báo giá chưa được chốt.')
    if (offer.material_code or '').strip().casefold() != (material_code or '').strip().casefold():
        raise PlanningError(f'{material_code}: báo giá không đúng mã NPL.')


@transaction.atomic
def submit_price_review(*, request_id: int) -> SxNplPurchaseRequest:
    pr = SxNplPurchaseRequest.objects.select_for_update().prefetch_related('lines__quote_offer').get(
        pk=request_id, is_demo=False,
    )
    if pr.status != SxNplPurchaseRequest.STATUS_DRAFT:
        raise PlanningError('Chỉ gửi duyệt giá khi đơn còn nháp.')
    lines = list(pr.lines.all())
    if not lines:
        raise PlanningError('Đơn chưa có dòng NPL.')
    for ln in lines:
        if _q(ln.qty) <= 0:
            raise PlanningError(f'{ln.material_code}: số lượng phải lớn hơn 0.')
        assert_line_uses_chosen_quote(material_code=ln.material_code, offer=ln.quote_offer)
        if ln.supplier_id != ln.quote_offer.supplier_id:
            raise PlanningError(f'{ln.material_code}: nhà cung cấp không khớp giá đã chốt.')
        if _q(ln.unit_price) != _q(ln.quote_offer.unit_price):
            raise PlanningError(f'{ln.material_code}: đơn giá không khớp giá đã chốt.')
    pr.status = SxNplPurchaseRequest.STATUS_PRICE_REVIEW
    pr.price_return_note = ''
    pr.save(update_fields=['status', 'price_return_note'])
    return pr


@transaction.atomic
def approve_price_review(*, request_id: int, user=None) -> SxNplPurchaseRequest:
    pr = SxNplPurchaseRequest.objects.select_for_update().get(pk=request_id, is_demo=False)
    if pr.status != SxNplPurchaseRequest.STATUS_PRICE_REVIEW:
        raise PlanningError('Chỉ duyệt đơn đang chờ duyệt giá.')
    pr.status = SxNplPurchaseRequest.STATUS_PRICED
    pr.price_approved_by = user if getattr(user, 'pk', None) else None
    pr.price_approved_at = timezone.now()
    pr.price_return_note = ''
    pr.save(update_fields=['status', 'price_approved_by', 'price_approved_at', 'price_return_note'])
    return pr


@transaction.atomic
def return_price_review(*, request_id: int, note: str = '') -> SxNplPurchaseRequest:
    pr = SxNplPurchaseRequest.objects.select_for_update().get(pk=request_id, is_demo=False)
    if pr.status != SxNplPurchaseRequest.STATUS_PRICE_REVIEW:
        raise PlanningError('Chỉ trả đơn đang chờ duyệt giá.')
    pr.status = SxNplPurchaseRequest.STATUS_DRAFT
    pr.price_return_note = (note or '').strip()[:500]
    pr.price_approved_by = None
    pr.price_approved_at = None
    pr.save(update_fields=['status', 'price_return_note', 'price_approved_by', 'price_approved_at'])
    return pr
