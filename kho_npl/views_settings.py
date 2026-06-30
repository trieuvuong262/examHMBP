from django.contrib import messages
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from assessment.decorators import module_perm_required, module_perm_required_methods
from hrm.module_permissions import MODULE_KHO_NPL
from PortalJustPlay.list_search import get_search_query
from PortalJustPlay.pagination import paginate_queryset

from kho_npl.settings_registry import SETTINGS_SECTIONS, get_settings_section
from kho_npl.view_utils import nav_context, perm_context


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
    if not show_inactive:
        qs = qs.filter(is_active=True)
    if search_query:
        q = Q()
        for field in config['search_fields']:
            q |= Q(**{f'{field}__icontains': search_query})
        qs = qs.filter(q)
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
    if request.method == 'POST' and form.is_valid():
        obj = form.save()
        messages.success(request, f'Đã thêm {obj}.')
        return redirect('kho_npl:settings_list', section=section)
    return render(request, 'kho_npl/settings_form.html', {
        **nav_context('settings', user=request.user),
        **perm_context(request.user, 'settings'),
        'section': config,
        'form': form,
        'is_edit': False,
        'cancel_url': reverse('kho_npl:settings_list', kwargs={'section': section}),
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
