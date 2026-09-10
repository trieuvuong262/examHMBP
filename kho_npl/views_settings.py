from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from kho_npl.material_search import apply_smart_search
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.settings_registry import SETTINGS_SECTIONS, get_settings_section
from kho_npl.view_utils import nav_context, perm_context

_MATERIAL_FORM_URL_NAMES = frozenset({'material_create', 'material_edit'})


def _safe_material_form_next(request) -> str:
    """Chỉ nhận next về form tạo/sửa NPL trên cùng host."""
    next_url = (request.POST.get('next') or request.GET.get('next') or '').strip()
    if not next_url:
        return ''
    if not url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ''
    try:
        match = resolve(urlsplit(next_url).path)
    except Resolver404:
        return ''
    if match.namespace != 'kho_npl' or match.url_name not in _MATERIAL_FORM_URL_NAMES:
        return ''
    return next_url


def _append_query(url: str, **params) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: str(value) for key, value in params.items()})
    return urlunsplit(parts._replace(query=urlencode(query)))


def _settings_form_extra(config):
    if config.get('key') == 'mau':
        from kho_npl.choices import DEFAULT_MATERIAL_COLORS
        return {
            'color_palette': [(name, hex_code) for _, name, hex_code, _ in DEFAULT_MATERIAL_COLORS],
        }
    return {}


def _section_or_404(section: str):
    config = get_settings_section(section)
    if not config:
        raise Http404
    return config


@module_perm_required(MODULE_KHO_NPL, 'view')
def settings_list(request, section):
    config = _section_or_404(section)
    search_query = get_search_query(request)
    show_inactive = request.GET.get('inactive') == '1'
    model = config['model']
    qs = model.objects.all()
    if config['key'] == 'quy-cach':
        qs = qs.prefetch_related('levels__unit')
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search_query:
        qs = apply_smart_search(qs, search_query, tuple(config['search_fields']))
    qs = qs.order_by(*config['order_by'])
    page_obj, query_string = paginate_queryset(request, qs, per_page=30)
    return render(request, 'kho_npl/settings_list.html', {
        **nav_context('settings', user=request.user),
        **perm_context(request.user, 'settings'),
        'section': config,
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'show_inactive': show_inactive,
        'list_columns': config['list_columns'],
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='create', post='create')
def settings_create(request, section):
    config = _section_or_404(section)
    form_class = config['form_class']
    form = form_class(request.POST or None)
    next_url = _safe_material_form_next(request)
    cancel_url = next_url or reverse('kho_npl:settings_list', kwargs={'section': section})
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Đã thêm {obj}.')
        if next_url:
            if section == 'quy-cach':
                next_url = _append_query(next_url, select_specification=obj.pk)
            return redirect(next_url)
        return redirect('kho_npl:settings_list', section=section)
    return render(request, 'kho_npl/settings_form.html', {
        **nav_context('settings', user=request.user),
        **perm_context(request.user, 'settings'),
        'section': config,
        'form': form,
        'is_edit': False,
        'next_url': next_url,
        'cancel_url': cancel_url,
        **_settings_form_extra(config),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='update', post='update')
def settings_edit(request, section, pk):
    config = _section_or_404(section)
    obj = get_object_or_404(config['model'], pk=pk)
    form_class = config['form_class']
    form = form_class(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Đã cập nhật {obj}.')
        return redirect('kho_npl:settings_list', section=section)
    return render(request, 'kho_npl/settings_form.html', {
        **nav_context('settings', user=request.user),
        **perm_context(request.user, 'settings'),
        'section': config,
        'form': form,
        'is_edit': True,
        'obj': obj,
        'cancel_url': reverse('kho_npl:settings_list', kwargs={'section': section}),
        **_settings_form_extra(config),
    })


@module_perm_required_methods(MODULE_KHO_NPL, get='delete', post='delete')
def settings_deactivate(request, section, pk):
    config = _section_or_404(section)
    obj = get_object_or_404(config['model'], pk=pk)
    if request.method == 'POST':
        obj.is_active = False
        obj.save(update_fields=['is_active'])
        messages.success(request, f'Đã ngừng dùng {obj}.')
        return redirect('kho_npl:settings_list', section=section)
    return render(request, 'kho_npl/settings_confirm_deactivate.html', {
        **nav_context('settings', user=request.user),
        **perm_context(request.user, 'settings'),
        'section': config,
        'obj': obj,
    })


def settings_hub_items():
    items = []
    for key, config in SETTINGS_SECTIONS.items():
        count = config['model'].objects.filter(is_active=True).count()
        items.append({
            'key': key,
            'title': config['title'],
            'icon': config['icon'],
            'count': count,
        })
    return items
