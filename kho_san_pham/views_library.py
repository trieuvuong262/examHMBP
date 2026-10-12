"""Thư viện sản phẩm — master theo Style (gom SKU của Kho sản phẩm), liên kết hồ sơ Thiết kế và kế hoạch ra mắt."""

from __future__ import annotations

from django.db.models import Count, Max, Min, Q
from django.http import Http404
from django.shortcuts import render

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_KHO_SAN_PHAM
from PortalJustPlay.pagination import paginate_queryset

from kho_san_pham.catalog_models import ProductStyle
from kho_san_pham.models import Product
from kho_san_pham.view_utils import perm_context

STATUS_CHOICES = (
    ('active', 'Đang dùng'),
    ('inactive', 'Ngừng dùng'),
    ('all', 'Tất cả'),
)

DETAIL_TABS = (
    ('data', 'Dữ liệu chuẩn', 'bi-card-text'),
    ('sku', 'SKU', 'bi-upc-scan'),
    ('images', 'Hình ảnh', 'bi-images'),
    ('channels', 'Kênh bán', 'bi-shop'),
    ('history', 'Lịch sử', 'bi-clock-history'),
)
DETAIL_TAB_KEYS = {t[0] for t in DETAIL_TABS}


def _group_q(group: str) -> Q:
    return Q(catalog_type__code=group) | Q(catalog_type__code__startswith=f'{group}-')


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


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def library_list(request):
    from thiet_ke_sp import catalog

    g = request.GET
    status = g.get('status') or 'active'
    if status not in {k for k, _ in STATUS_CHOICES}:
        status = 'active'
    q = (g.get('q') or '').strip()
    group = (g.get('group') or '').strip().upper()

    qs = Product.objects.exclude(style_code='')
    if status == 'active':
        qs = qs.filter(is_active=True)
    elif status == 'inactive':
        qs = qs.exclude(style_code__in=Product.objects.filter(is_active=True).exclude(style_code='').values('style_code'))
    if q:
        qs = qs.filter(
            Q(style_code__icontains=q) | Q(name__icontains=q) | Q(code__icontains=q)
            | Q(category_name__icontains=q) | Q(kiotviet_code__icontains=q)
        )
    if group:
        qs = qs.filter(_group_q(group))
    rows = (
        qs.values('style_code')
        .annotate(
            sku_count=Count('pk'),
            color_count=Count('color_code', distinct=True),
            size_count=Count('size_label', distinct=True),
            active_count=Count('pk', filter=Q(is_active=True)),
            kv_count=Count('kiotviet_id'),
            min_price=Min('base_price'),
            max_price=Max('base_price'),
            last_update=Max('updated_at'),
        )
        .order_by('-last_update', 'style_code')
    )
    page_obj, query_string = paginate_queryset(request, rows, per_page=40)
    items = list(page_obj.object_list)
    codes = [r['style_code'] for r in items]

    styles = {s.code: s for s in ProductStyle.objects.filter(code__in=codes).select_related('product_type')}
    reps: dict[str, Product] = {}
    colors: dict[str, list[str]] = {}
    sizes: dict[str, list[str]] = {}
    for p in Product.objects.filter(style_code__in=codes).select_related('catalog_type').order_by('style_code', 'pk'):
        rep = reps.get(p.style_code)
        if rep is None or (not rep.display_image_url and p.display_image_url):
            reps[p.style_code] = p
        label = p.color_label or p.color_code
        if label and label not in colors.setdefault(p.style_code, []):
            colors[p.style_code].append(label)
        if p.size_label and p.size_label not in sizes.setdefault(p.style_code, []):
            sizes[p.style_code].append(p.size_label)
    dossiers = _dossiers_by_style(codes)
    for r in items:
        code = r['style_code']
        style = styles.get(code)
        rep = reps.get(code)
        ptype = style.product_type if style else (rep.catalog_type if rep else None)
        r['name'] = (style.name if style and style.name else '') or (rep.name if rep else code)
        r['type_code'] = ptype.code if ptype else ''
        r['group_label'] = catalog.group_label(catalog.group_code(ptype.code)) if ptype else (rep.category_name if rep else '')
        r['image_url'] = rep.display_image_url if rep else ''
        r['colors'] = colors.get(code, [])
        r['sizes'] = sizes.get(code, [])
        r['dossier'] = dossiers.get(code.upper())
        r['is_active'] = r['active_count'] > 0
    total_styles = Product.objects.exclude(style_code='').values('style_code').distinct().count()
    no_style = Product.objects.filter(style_code='', is_active=True).count()
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
        'total_styles': total_styles,
        'no_style': no_style,
    })


@module_perm_required(MODULE_KHO_SAN_PHAM, 'view')
def library_detail(request, style):
    from thiet_ke_sp import catalog

    code = (style or '').strip().upper()
    products = list(Product.objects.filter(style_code=code).select_related('catalog_type', 'created_by__profile'))
    style_obj = ProductStyle.objects.filter(code=code).select_related('product_type', 'created_by__profile').first()
    if not products and style_obj is None:
        raise Http404('Không có Style này trong thư viện.')
    tab = request.GET.get('tab') or 'data'
    if tab not in DETAIL_TAB_KEYS:
        tab = 'data'
    rep = next((p for p in products if p.display_image_url), products[0] if products else None)
    ptype = style_obj.product_type if style_obj else (rep.catalog_type if rep else None)
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
    dossier = _dossiers_by_style([code]).get(code)
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
        if p.synced_at:
            history.append({'at': p.synced_at, 'text': f'Đồng bộ KiotViet {p.code}', 'user': None})
        if p.updated_at and p.updated_at != p.created_at:
            history.append({'at': p.updated_at, 'text': f'Cập nhật SKU {p.code}', 'user': None})
    history.sort(key=lambda h: h['at'], reverse=True)
    return render(request, 'kho_san_pham/library_detail.html', {
        **perm_context(request.user, 'products'),
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
        'kv_count': sum(1 for p in products if p.kiotviet_id),
        'qty_total': sum((p.qty_on_hand or 0) for p in products),
        'dossier': dossier,
        'launches': launches,
        'history': history[:100],
        'tab': tab,
        'tabs': DETAIL_TABS,
    })
