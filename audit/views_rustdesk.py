from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required
from audit.forms_rustdesk import RustDeskHostForm
from audit.models import RustDeskHost
from hrm.menu_permissions import user_can_delete_menu, user_can_edit_menu
from hrm.module_permissions import MODULE_AUDIT
from PortalJustPlay.pagination import paginate_queryset


def _rustdesk_public_host() -> str:
    return getattr(settings, 'RUSTDESK_PUBLIC_HOST', 'rd.justplay.vn')


RUSTDESK_MENU_KEY = 'rustdesk'


def _can_connect(user) -> bool:
    return user_can_edit_menu(user, MODULE_AUDIT, RUSTDESK_MENU_KEY)


def _can_delete(user) -> bool:
    return user_can_delete_menu(user, MODULE_AUDIT, RUSTDESK_MENU_KEY)


@module_perm_required(MODULE_AUDIT, 'view')
def rustdesk_list(request):
    qs = RustDeskHost.objects.select_related('device').all()

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(hostname__icontains=q)
            | Q(ip_address__icontains=q)
            | Q(rustdesk_id__icontains=q)
            | Q(department_text__icontains=q)
            | Q(assigned_user_text__icontains=q)
        )

    active = request.GET.get('active')
    if active == '1':
        qs = qs.filter(is_active=True)
    elif active == '0':
        qs = qs.filter(is_active=False)

    qs = qs.order_by('name', 'rustdesk_id')
    filtered_count = qs.count()
    page_obj, query_string = paginate_queryset(request, qs)

    return render(request, 'audit/rustdesk_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'q': q,
        'current_active': active,
        'filtered_count': filtered_count,
        'can_connect_rustdesk': _can_connect(request.user),
        'can_edit_rustdesk': _can_connect(request.user),
        'rustdesk_public_host': _rustdesk_public_host(),
    })


@module_perm_required(MODULE_AUDIT, 'create')
def rustdesk_add(request):
    if request.method == 'POST':
        form = RustDeskHostForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã thêm máy RustDesk.')
            return redirect('audit:rustdesk_list')
    else:
        form = RustDeskHostForm()
    return render(request, 'audit/rustdesk_form.html', {
        'form': form,
        'title': 'Thêm máy RustDesk',
        'rustdesk_public_host': _rustdesk_public_host(),
    })


@module_perm_required(MODULE_AUDIT, 'update')
def rustdesk_edit(request, pk):
    host = get_object_or_404(RustDeskHost, pk=pk)
    if request.method == 'POST':
        form = RustDeskHostForm(request.POST, instance=host)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật máy RustDesk.')
            return redirect('audit:rustdesk_list')
    else:
        form = RustDeskHostForm(instance=host)
    return render(request, 'audit/rustdesk_form.html', {
        'form': form,
        'host': host,
        'title': 'Sửa máy RustDesk',
        'rustdesk_public_host': _rustdesk_public_host(),
        'can_delete_rustdesk': _can_delete(request.user),
    })


@module_perm_required(MODULE_AUDIT, 'delete')
@require_POST
def rustdesk_delete(request, pk):
    host = get_object_or_404(RustDeskHost, pk=pk)
    label = str(host)
    host.delete()
    messages.success(request, f'Đã xóa {label}.')
    return redirect('audit:rustdesk_list')
