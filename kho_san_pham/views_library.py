"""Thư viện sản phẩm — master theo Style (gom SKU của Kho sản phẩm), liên kết hồ sơ Thiết kế và kế hoạch ra mắt."""

from __future__ import annotations

from django.contrib import messages
from django.db.models import (
    Count, DateTimeField, DecimalField, Exists, F, IntegerField, Max, Min, OuterRef, Q, Subquery, Sum,
)
from django.db.models.functions import Coalesce, Greatest
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.pagination import paginate_queryset

from san_xuat.list_grid import SX_LIST_GRIDS, sx_list_grid_context

from kho_san_pham.catalog_models import ProductStyle
from kho_san_pham.choices import STYLE_SOURCE_DESIGN
from kho_san_pham.library_grid import LIST_KEY
from kho_san_pham.models import Product
from kho_san_pham.view_utils import perm_context

STATUS_CHOICES = (
    ('all', 'Tất cả'),
    ('pending', 'Chờ chuyển SX'),
    ('transferred', 'Đã chuyển SX'),
    ('inactive', 'Ngừng dùng'),
)

DETAIL_TABS = (
    ('data', 'Dữ liệu chuẩn', 'bi-card-text'),
    ('sku', 'SKU', 'bi-upc-scan'),
    ('prices', 'Giá bán', 'bi-cash-coin'),
    ('images', 'Hình ảnh', 'bi-images'),
    ('history', 'Lịch sử', 'bi-clock-history'),
)
DETAIL_TAB_KEYS = {t[0] for t in DETAIL_TABS}


def _dossier_covers(dossiers) -> dict[int, str]:
    from thiet_ke_sp.presenters import cover_map

    ids = [d.pk for d in dossiers]
    return {pk: att.get_absolute_url() for pk, att in cover_map(ids).items() if att} if ids else {}


def _style_avatar_url(dossier, rep, covers: dict[int, str] | None = None) -> str:
    """Ảnh đại diện Style: ảnh hồ sơ thiết kế, không có thì ảnh SKU."""
    if dossier is not None:
        if covers is None:
            covers = _dossier_covers([dossier])
        cover = covers.get(dossier.pk, '')
        if cover:
            return cover
    return (rep.display_image_url if rep else '') or ''


def _dossiers_by_style(codes) -> dict[str, object]:
    from thiet_ke_sp.models import ProductDevelopment

    if not codes:
        return {}
    q = Q()
    for c in codes:
        q |= Q(official_product_code__iexact=c)
    out = {}
    for d in ProductDevelopment.objects.filter(q).order_by('-created_at'):
        out.setdefault((d.official_product_code or '').strip().upper(), d)
    return out


def _sku_agg(expr, output):
    sub = (
        Product.objects.filter(style_code=OuterRef('code'))
        .order_by().values('style_code').annotate(v=expr).values('v')
    )
    return Subquery(sub, output_field=output)


def _shelf_codes():
    """Style đang hiện trong Thư viện: hồ sơ đã thêm hoặc đã đóng."""
    from thiet_ke_sp.models import Handover, Status

    return Handover.objects.filter(
        dossier__status__in=(Status.HANDED_OVER, Status.CLOSED),
    ).values('product_code')


def _off_shelf_redirect(request, code):
    """Style đã gỡ để chỉnh hồ sơ thì không mở trang Thư viện."""
    handover = _handovers_by_code([code]).get((code or '').strip().upper())
    if handover is None or handover.dossier.status in ('handed_over', 'closed'):
        return None
    messages.info(request, 'Style đang được chỉnh trên hồ sơ thiết kế nên tạm ẩn khỏi Thư viện.')
    return redirect(handover.dossier.get_absolute_url())


def _handovers_by_code(codes) -> dict:
    from thiet_ke_sp.models import Handover

    if not codes:
        return {}
    rows = Handover.objects.filter(product_code__in=codes).select_related(
        'dossier', 'dossier__approved_design_version', 'design_version',
        'transferred_by__profile', 'tech_doc')
    return {h.product_code.upper(): h for h in rows}


def _sku_colorway_map(dossier, handover) -> dict[str, dict]:
    """Colorway thiết kế khớp với nhãn màu trên SKU."""
    from thiet_ke_sp.models import Attachment, AttachmentKind
    from thiet_ke_sp.services.workflow import _library_color_label

    dv = None
    if handover is not None and handover.design_version_id:
        dv = handover.design_version
    elif dossier is not None and dossier.approved_design_version_id:
        dv = dossier.approved_design_version
    if dv is None:
        return {}
    colorways = list(dv.colorways.all())
    if not colorways:
        return {}
    images: dict[int, str] = {}
    attachments = (
        Attachment.objects.filter(
            colorway__in=colorways,
            kind=AttachmentKind.COLORWAY,
            is_deleted=False,
            is_current=True,
        )
        .exclude(file='')
        .order_by('colorway_id', '-uploaded_at', '-pk')
    )
    for att in attachments:
        images.setdefault(att.colorway_id, att.get_absolute_url())
    out: dict[str, dict] = {}
    for cw in colorways:
        info = {
            'name': cw.name,
            'codes': (cw.color_codes or '').strip(),
            'url': images.get(cw.pk, ''),
        }
        for key in (_library_color_label(cw), (cw.name or '').strip()):
            if key:
                out.setdefault(key.casefold(), info)
    return out


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def library_list(request):
    from thiet_ke_sp import catalog
    from thiet_ke_sp.models import Handover

    g = request.GET
    status = g.get('status') or 'all'
    if status not in {k for k, _ in STATUS_CHOICES}:
        status = 'all'
    q = (g.get('q') or '').strip()
    group = (g.get('group') or '').strip().upper()

    base = ProductStyle.objects.filter(source=STYLE_SOURCE_DESIGN, code__in=_shelf_codes())
    transferred = Exists(Handover.objects.filter(product_code=OuterRef('code'), tech_doc__isnull=False))
    has_handover = Exists(Handover.objects.filter(product_code=OuterRef('code')))
    qs = base.select_related('product_type').annotate(
        style_code=F('code'),
        transferred=transferred,
        has_handover=has_handover,
        sku_count=Coalesce(_sku_agg(Count('pk'), IntegerField()), 0),
        min_price=_sku_agg(Min('base_price'), DecimalField(max_digits=18, decimal_places=2)),
        qty_total=_sku_agg(Sum('qty_on_hand'), DecimalField(max_digits=18, decimal_places=3)),
        kv_count=Coalesce(_sku_agg(Count('kiotviet_id'), IntegerField()), 0),
        last_update=Greatest('updated_at', Coalesce(_sku_agg(Max('updated_at'), DateTimeField()), 'updated_at')),
    )
    if status == 'inactive':
        qs = qs.filter(is_active=False)
    else:
        qs = qs.filter(is_active=True)
        if status == 'pending':
            qs = qs.filter(transferred=False)
        elif status == 'transferred':
            qs = qs.filter(transferred=True)
    if q:
        sku_hit = Product.objects.filter(
            Q(code__icontains=q) | Q(name__icontains=q) | Q(kiotviet_code__icontains=q)).values('style_code')
        qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q) | Q(code__in=sku_hit))
    if group:
        qs = qs.filter(Q(product_type__code=group) | Q(product_type__code__startswith=f'{group}-'))
    grid = sx_list_grid_context(request, LIST_KEY)
    sort_field = SX_LIST_GRIDS[LIST_KEY]['sort_fields'][grid['sort_key']]
    prefix = '-' if grid['sort_dir'] == 'desc' else ''
    qs = qs.order_by(f'{prefix}{sort_field}', 'code')
    page_obj, query_string = paginate_queryset(request, qs, per_page=40)
    styles = {s.code: s for s in page_obj.object_list}
    codes = list(styles)
    items = [{
        'style_code': s.code, 'sku_count': s.sku_count, 'min_price': s.min_price, 'qty_total': s.qty_total,
        'kv_count': s.kv_count, 'transferred': s.transferred, 'style_active': s.is_active,
        'can_transfer': bool(s.is_active and s.has_handover and not s.transferred),
    } for s in styles.values()]
    reps: dict[str, Product] = {}
    colors: dict[str, list[str]] = {}
    sizes: dict[str, list[str]] = {}
    ready_codes: set[str] = set()
    for p in Product.objects.filter(style_code__in=codes).select_related('catalog_type').order_by('style_code', 'pk'):
        if (p.color_code or '').strip() and (p.size_label or '').strip():
            ready_codes.add(p.style_code)
        rep = reps.get(p.style_code)
        if rep is None or (not rep.display_image_url and p.display_image_url):
            reps[p.style_code] = p
        label = p.color_label or p.color_code
        if label and label not in colors.setdefault(p.style_code, []):
            colors[p.style_code].append(label)
        if p.size_label and p.size_label not in sizes.setdefault(p.style_code, []):
            sizes[p.style_code].append(p.size_label)
    dossiers = _dossiers_by_style(codes)
    covers = _dossier_covers(dossiers.values())
    for r in items:
        code = r['style_code']
        style = styles[code]
        rep = reps.get(code)
        dossier = dossiers.get(code.upper())
        r['can_transfer'] = r['can_transfer'] and code in ready_codes
        r['name'] = style.name or (rep.name if rep else code)
        r['type_code'] = style.product_type.code
        r['group_label'] = catalog.group_label(catalog.group_code(style.product_type.code))
        r['image_url'] = _style_avatar_url(dossier, rep, covers)
        r['colors'] = colors.get(code, [])
        r['sizes'] = sizes.get(code, [])
        r['dossier'] = dossier
    active = base.filter(is_active=True)
    pending_count = active.exclude(
        code__in=Handover.objects.filter(tech_doc__isnull=False).values('product_code')).count()
    return render(request, 'kho_san_pham/library_list.html', {
        **perm_context(request.user, 'products'),
        'page_obj': page_obj,
        'items': items,
        'query_string': query_string,
        'q': q,
        'status': status,
        'status_choices': STATUS_CHOICES,
        'group': group,
        'group_choices': catalog.group_choices(),
        'total_styles': active.count(),
        'matched_count': page_obj.paginator.count,
        'pending_count': pending_count,
        'has_filters': bool(q or group or status != 'all'),
        **grid,
    })


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def library_detail(request, style):
    from thiet_ke_sp import catalog

    code = (style or '').strip().upper()
    style_obj = ProductStyle.objects.filter(code=code).select_related('product_type', 'created_by__profile').first()
    if style_obj is None or style_obj.source != STYLE_SOURCE_DESIGN:
        if style_obj is None and not Product.objects.filter(style_code=code).exists():
            raise Http404('Không có Style này trong thư viện.')
        return redirect(f"{reverse('kho_san_pham:product_list')}?q={code}&status=all")
    hidden = _off_shelf_redirect(request, code)
    if hidden:
        return hidden
    products = list(
        Product.objects.filter(style_code=code)
        .select_related('catalog_type', 'created_by__profile')
        .order_by('color_code', 'size_label', 'code')
    )
    handover = _handovers_by_code([code]).get(code)
    receipts = list(handover.receipts.select_related('receiver__profile')) if handover else []
    tab = request.GET.get('tab') or 'data'
    if tab not in DETAIL_TAB_KEYS:
        tab = 'data'
    rep = next((p for p in products if p.display_image_url), products[0] if products else None)
    ptype = style_obj.product_type
    prices = [p.base_price for p in products if p.base_price is not None]
    images = []
    seen = set()
    for p in products:
        url = p.display_image_url
        if url and url not in seen:
            seen.add(url)
            images.append({'url': url, 'label': p.color_label or p.color_code or p.code, 'sku': p.code})
    colors = []
    for p in products:
        label = p.color_label or p.color_code
        if label and label not in colors:
            colors.append(label)
    sizes = []
    for p in products:
        if p.size_label and p.size_label not in sizes:
            sizes.append(p.size_label)
    dossier = handover.dossier if handover else _dossiers_by_style([code]).get(code)
    colorways = _sku_colorway_map(dossier, handover)
    for product in products:
        info = colorways.get((product.color_label or '').strip().casefold()) or {}
        product.cw_name = info.get('name') or ''
        product.cw_codes = info.get('codes') or ''
        product.cw_image = info.get('url') or ''
    cover_url = _style_avatar_url(dossier, rep)
    if cover_url and all(img['url'] != cover_url for img in images):
        images.insert(0, {'url': cover_url, 'label': 'Ảnh đại diện', 'sku': code})
    launches = []
    if dossier:
        from ra_mat_sp.models import LaunchPlan

        launches = list(LaunchPlan.objects.filter(products__dossier=dossier).order_by('-launch_date'))
    history = []
    if style_obj:
        history.append({'at': style_obj.created_at, 'text': f'Tạo Style ({style_obj.get_source_display()})',
                        'user': style_obj.created_by})
        if style_obj.updated_at and style_obj.updated_at != style_obj.created_at:
            history.append({'at': style_obj.updated_at, 'text': 'Cập nhật thông tin Style', 'user': None})
    for p in products:
        history.append({'at': p.created_at, 'text': f'Tạo SKU {p.code}', 'user': p.created_by})
        if p.updated_at and p.updated_at != p.created_at:
            history.append({'at': p.updated_at, 'text': f'Cập nhật SKU {p.code}', 'user': None})
    if handover:
        history.append({
            'at': handover.handed_at, 'text': 'Thiết kế bàn giao vào Thư viện',
            'user': handover.handed_by, 'status': True,
        })
        if handover.transferred_at:
            history.append({
                'at': handover.transferred_at, 'text': 'Chuyển sang sản xuất',
                'user': handover.transferred_by, 'status': True,
            })
    history.sort(key=lambda h: h['at'], reverse=True)
    completeness_items = [
        ('Hình ảnh', bool(images)),
        ('Giá bán', bool(prices)),
        ('Màu', bool(colors)),
        ('Size', bool(sizes)),
        ('Hồ sơ thiết kế', bool(dossier)),
        ('Đã chuyển sản xuất', bool(handover and handover.is_transferred)),
    ]
    from kho_san_pham.library_release import style_transfer_block

    perms_ctx = perm_context(request.user, 'products')
    transfer_block = style_transfer_block(code) if handover and not handover.is_transferred else ''
    can_transfer = bool(
        perms_ctx['can_update'] and handover and not handover.is_transferred
        and handover.dossier.status == 'handed_over' and style_obj.is_active
        and not transfer_block
    )
    return render(request, 'kho_san_pham/library_detail.html', {
        **perms_ctx,
        'handover': handover,
        'receipts': receipts,
        'can_transfer': can_transfer,
        'transfer_block': transfer_block,
        'code': code,
        'style': style_obj,
        'products': products,
        'rep': rep,
        'name': (style_obj.name if style_obj and style_obj.name else '') or (rep.name if rep else code),
        'ptype': ptype,
        'group_label': catalog.group_label(catalog.group_code(ptype.code)) if ptype else '',
        'min_price': min(prices) if prices else None,
        'max_price': max(prices) if prices else None,
        'images': images,
        'colors': colors,
        'sizes': sizes,
        'active_count': sum(1 for p in products if p.is_active),
        'dossier': dossier,
        'launches': launches,
        'history': history[:100],
        'tab': tab,
        'tabs': DETAIL_TABS,
        'completeness_items': completeness_items,
        'completeness': round(100 * sum(1 for _, ok in completeness_items if ok) / len(completeness_items)),
        'cover_url': cover_url,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
@require_POST
def library_prices_save(request, style):
    """Lưu giá bán hàng loạt theo từng SKU của Style."""
    from decimal import Decimal

    from django.utils import timezone

    from kho_san_pham.forms import parse_vnd_integer

    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    products = {
        p.pk: p
        for p in Product.objects.filter(style_code=obj.code).only('pk', 'code', 'base_price')
    }
    if not products:
        messages.warning(request, 'Style chưa có SKU để chỉnh giá.')
        return redirect(_library_tab(obj.code, 'prices'))

    updated = 0
    errors = []
    now = timezone.now()
    with transaction.atomic():
        for pk, product in products.items():
            raw = (request.POST.get(f'price_{pk}') or '').strip()
            if not raw:
                continue
            try:
                value = parse_vnd_integer(raw)
            except (ValueError, TypeError):
                errors.append(product.code)
                continue
            if value is None:
                value = Decimal('0')
            if value < 0:
                errors.append(product.code)
                continue
            if product.base_price == value:
                continue
            product.base_price = value
            product.updated_at = now
            product.save(update_fields=['base_price', 'updated_at'])
            updated += 1

    if errors:
        messages.error(request, 'Giá không hợp lệ cho: ' + ', '.join(errors[:8]) + ('…' if len(errors) > 8 else ''))
    if updated:
        messages.success(request, f'Đã cập nhật giá bán {updated} SKU.')
    elif not errors:
        messages.info(request, 'Không có thay đổi giá bán.')
    return redirect(_library_tab(obj.code, 'prices'))


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, post='update')
@require_POST
def library_transfer(request, style):
    from thiet_ke_sp.services import workflow as wf

    code = (style or '').strip().upper()
    hidden = _off_shelf_redirect(request, code)
    if hidden:
        return hidden
    detail_url = reverse('kho_san_pham:library_detail', args=[code])
    handover = _handovers_by_code([code]).get(code)
    if handover is None or not ProductStyle.objects.filter(
            code=code, source=STYLE_SOURCE_DESIGN, is_active=True).exists():
        messages.error(request, 'Style này không có bàn giao từ Thiết kế đang chờ chuyển sản xuất.')
        return redirect(detail_url)
    try:
        tech_doc = wf.transfer_to_production(handover, request.user)
    except wf.WorkflowError as exc:
        messages.error(request, str(exc))
        return redirect(detail_url)
    messages.success(request, f'Đã chuyển {code} sang sản xuất — tạo hồ sơ sản phẩm SX {tech_doc.product_code}.')
    return redirect(detail_url)


def _design_style(code: str) -> ProductStyle:
    code = (code or '').strip().upper()
    style = (
        ProductStyle.objects.filter(code=code, source=STYLE_SOURCE_DESIGN)
        .select_related('product_type')
        .first()
    )
    if style is None:
        raise Http404('Không có Style này trong thư viện.')
    return style


def _library_tab(code: str, tab: str = 'sku') -> str:
    return f"{reverse('kho_san_pham:library_detail', args=[code])}?tab={tab}"


def _library_product(style: ProductStyle, pk: int) -> Product:
    return get_object_or_404(Product, pk=pk, style_code=style.code)


def _sku_initial(style: ProductStyle, source: Product | None = None) -> dict:
    from thiet_ke_sp import catalog

    from kho_san_pham.choices import PRODUCT_TYPE_THANH_PHAM, goods_product_type
    from kho_san_pham.views import _clone_form_initial

    if source is not None:
        initial = _clone_form_initial(source)
        initial['style_code'] = style.code
        if style.name:
            initial['name'] = style.name
        return initial
    type_code = style.product_type.code if style.product_type_id else ''
    return {
        'is_active': True,
        'product_type': goods_product_type(catalog_type_code=type_code) if type_code else PRODUCT_TYPE_THANH_PHAM,
        'catalog_type': style.product_type_id,
        'style_code': style.code,
        'name': style.name,
        'full_name': style.name,
        'category_name': catalog.group_label(catalog.group_code(type_code)) if type_code else '',
    }


def _library_form_page(request, form, style: ProductStyle, **extra):
    return render(request, 'kho_san_pham/product_form.html', {
        **perm_context(request.user, 'products'),
        'form': form,
        'library_code': style.code,
        'library_style': style,
        'cancel_url': _library_tab(style.code),
        **extra,
    })


def _save_library_sku(form, request, *, source: Product | None = None) -> Product:
    from kho_san_pham.choices import SYNC_SOURCE_MANUAL
    from kho_san_pham.services.barcode import allocate_barcode
    from kho_san_pham.views import _apply_catalog_qty

    product = form.save(commit=False)
    if form.locked_style:
        product.style_code = form.locked_style
    if not product.pk:
        product.sync_source = SYNC_SOURCE_MANUAL
        product.created_by = request.user
        if source is not None:
            product.gender = source.gender
            product.category_path = source.category_path
            product.allows_sale = source.allows_sale
            if not product.image and source.image:
                product.image = source.image
            if not (product.image_url or '').strip():
                product.image_url = source.image_url or ''
        if not (product.bar_code or '').strip():
            product.bar_code = allocate_barcode()
    product.save()
    _apply_catalog_qty(product, form, user=request.user)
    return product


def _save_library_sku_variants(form, request, *, source: Product | None = None) -> tuple[list[Product], list[dict]]:
    """Tạo nhiều SKU theo tổ hợp màu × size đã chọn."""
    from decimal import Decimal

    from kho_san_pham.choices import SYNC_SOURCE_MANUAL
    from kho_san_pham.services.barcode import allocate_barcode
    from kho_san_pham.views import _apply_catalog_qty

    cd = form.cleaned_data
    create_rows = cd.get('variant_create') or []
    skip_rows = cd.get('variant_skip') or []
    created: list[Product] = []
    shared_image = None
    uploaded = form.files.get('image') if getattr(form, 'files', None) else None

    for index, row in enumerate(create_rows):
        product = Product(
            product_type=cd.get('product_type'),
            catalog_type=cd.get('catalog_type'),
            style_code=form.locked_style or cd.get('style_code') or '',
            color_code=row['color_code'],
            color_label=row['color_label'],
            size_label=row['size_label'],
            code=row['code'],
            accounting_code=cd.get('accounting_code') or '',
            kiotviet_code=cd.get('kiotviet_code') or '',
            name=(cd.get('name') or '').strip() or (form.locked_style or row['code']),
            full_name=cd.get('full_name') or '',
            unit=cd.get('unit') or '',
            category_name=cd.get('category_name') or '',
            base_price=cd.get('base_price') if cd.get('base_price') is not None else Decimal('0'),
            description=cd.get('description') or '',
            notes=cd.get('notes') or '',
            is_active=bool(cd.get('is_active', True)),
            sync_source=SYNC_SOURCE_MANUAL,
            created_by=request.user,
            bar_code=allocate_barcode(),
        )
        if source is not None:
            product.gender = source.gender
            product.category_path = source.category_path
            product.allows_sale = source.allows_sale
            if not (product.image_url or '').strip():
                product.image_url = source.image_url or ''
        if index == 0 and uploaded is not None:
            product.image = uploaded
        elif shared_image:
            product.image = shared_image
        elif source is not None and source.image:
            product.image = source.image
        product.save()
        if index == 0:
            shared_image = product.image or (source.image if source is not None else None)
        if product.style_code and product.size_label:
            try:
                from san_xuat.services.sku_catalog import get_or_create_sku
                display_code = product.code
                sx = get_or_create_sku(
                    style_code=product.style_code,
                    color_code=product.color_code or '',
                    size_label=product.size_label,
                    color_label=product.color_label,
                    style_name=product.name,
                    gender=product.gender,
                    user=request.user,
                )
                product.sx_sku = sx
                product.code = display_code
                product.save(update_fields=['sx_sku', 'code', 'updated_at'])
            except Exception:  # noqa: BLE001
                pass
        _apply_catalog_qty(product, form, user=request.user)
        created.append(product)
    return created, skip_rows


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def library_style_edit(request, style):
    from kho_san_pham.catalog_forms import ProductStyleEditForm

    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    old_name = obj.name
    form = ProductStyleEditForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        renamed = 0
        if request.POST.get('rename_skus') and old_name != obj.name:
            from django.utils import timezone
            renamed = Product.objects.filter(style_code=obj.code, name=old_name).update(
                name=obj.name, updated_at=timezone.now(),
            )
        msg = f'Đã cập nhật tên {obj.code}.'
        if renamed:
            msg += f' Đổi tên {renamed} SKU.'
        messages.success(request, msg)
        return redirect(_library_tab(obj.code, 'data'))
    return render(request, 'kho_san_pham/style_form.html', {
        **perm_context(request.user, 'products'),
        'form': form,
        'is_edit': True,
        'style': obj,
        'show_rename_skus': Product.objects.filter(style_code=obj.code).exists(),
        'cancel_url': _library_tab(obj.code, 'data'),
        'library_code': obj.code,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def library_sku_create(request, style):
    from kho_san_pham.forms import ProductForm
    from kho_san_pham.services.stock import StockMovementError

    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    source = Product.objects.filter(style_code=obj.code).order_by('pk').first()
    form = ProductForm(
        request.POST or None,
        request.FILES or None,
        initial=_sku_initial(obj, source),
        clone_from=source,
        locked_style=obj.code,
        multi_variant=True,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                created, skipped = _save_library_sku_variants(form, request, source=source)
        except StockMovementError as exc:
            messages.error(request, str(exc))
        else:
            msg = f'Đã thêm {len(created)} SKU vào Thư viện.'
            if skipped:
                msg += f' Bỏ qua {len(skipped)} tổ hợp đã có.'
            messages.success(request, msg)
            return redirect(_library_tab(obj.code))
    return _library_form_page(
        request, form, obj,
        is_edit=False,
        suggest_variant=source is not None,
        source_product=source,
        multi_variant=True,
    )


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def library_sku_edit(request, style, pk: int):
    from kho_san_pham.forms import ProductForm
    from kho_san_pham.services.stock import StockMovementError

    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    product = _library_product(obj, pk)
    form = ProductForm(
        request.POST or None, request.FILES or None, instance=product, locked_style=obj.code,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = _save_library_sku(form, request)
        except StockMovementError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã cập nhật {product.code}.')
            return redirect(_library_tab(obj.code))
    return _library_form_page(request, form, obj, is_edit=True, product=product)


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='create', post='create')
def library_sku_duplicate(request, style, pk: int):
    from kho_san_pham.forms import ProductForm
    from kho_san_pham.services.stock import StockMovementError

    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    source = _library_product(obj, pk)
    form = ProductForm(
        request.POST or None,
        request.FILES or None,
        initial=_sku_initial(obj, source),
        clone_from=source,
        locked_style=obj.code,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                product = _save_library_sku(form, request, source=source)
        except StockMovementError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f'Đã nhân bản {source.code} thành {product.code}.')
            return redirect(_library_tab(obj.code))
    return _library_form_page(
        request, form, obj, is_edit=False, is_duplicate=True, source_product=source,
    )


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def library_sku_deactivate(request, style, pk: int):
    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    product = _library_product(obj, pk)
    back = _library_tab(obj.code)
    if request.method == 'POST':
        product.is_active = False
        product.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Đã ngừng dùng {product.code}.')
        return redirect(back)
    return render(request, 'kho_san_pham/product_confirm_deactivate.html', {
        **perm_context(request.user, 'products'),
        'product': product,
        'cancel_url': back,
        'library_code': obj.code,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='update', post='update')
def library_sku_reactivate(request, style, pk: int):
    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    product = _library_product(obj, pk)
    back = _library_tab(obj.code)
    if request.method == 'POST':
        product.is_active = True
        product.save(update_fields=['is_active', 'updated_at'])
        messages.success(request, f'Đã dùng lại {product.code}.')
        return redirect(back)
    return render(request, 'kho_san_pham/product_confirm_reactivate.html', {
        **perm_context(request.user, 'products'),
        'product': product,
        'cancel_url': back,
        'library_code': obj.code,
    })


@module_perm_required_methods(MODULE_KHO_SAN_PHAM, get='delete', post='delete')
def library_sku_delete(request, style, pk: int):
    from django.db.models.deletion import ProtectedError

    from kho_san_pham.views import _product_delete_blockers

    hidden = _off_shelf_redirect(request, style)
    if hidden:
        return hidden
    obj = _design_style(style)
    product = _library_product(obj, pk)
    back = _library_tab(obj.code)
    blockers = _product_delete_blockers(product)
    if request.method == 'POST':
        try:
            with transaction.atomic():
                product = get_object_or_404(Product.objects.select_for_update(), pk=pk, style_code=obj.code)
                blockers = _product_delete_blockers(product)
                if blockers:
                    messages.error(
                        request,
                        f'Không thể xóa {product.code} vì đã có dữ liệu phát sinh. '
                        'Hãy dùng “Ngừng dùng” để giữ lịch sử.',
                    )
                    return redirect(back)
                code = product.code
                image = product.image
                product.stock_balances.filter(qty_on_hand=0).delete()
                product.delete()
                if image:
                    transaction.on_commit(lambda: image.delete(save=False))
        except ProtectedError:
            messages.error(request, f'Không thể xóa {product.code} vì đang được dữ liệu khác sử dụng.')
            return redirect(back)
        messages.success(request, f'Đã xóa {code} khỏi Thư viện.')
        return redirect(back)
    return render(request, 'kho_san_pham/product_confirm_delete.html', {
        **perm_context(request.user, 'products'),
        'product': product,
        'delete_blockers': blockers,
        'cancel_url': back,
        'deactivate_url': reverse('kho_san_pham:library_sku_deactivate', args=[obj.code, product.pk]),
        'scope_label': 'Thư viện',
        'library_code': obj.code,
    })
