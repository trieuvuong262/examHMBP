from django.conf import settings
from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from assessment.decorators import module_perm_required
from audit.forms_rustdesk import RustDeskHostForm
from audit.models import RustDeskHost
from audit.services.rustdesk_device_sync import sync_all_rustdesk_hosts_from_devices
from audit.services.rustdesk_connect import effective_rustdesk_password
from audit.services.rustdesk_online import get_peers_online_map, normalize_rustdesk_id
from audit.services.wake_on_lan import dispatch_wake_on_lan
from hrm.menu_permissions import user_can_access_menu, user_can_delete_menu, user_can_edit_menu
from hrm.module_permissions import MODULE_AUDIT
from PortalJustPlay.pagination import paginate_queryset


def _rustdesk_public_host() -> str:
    return getattr(settings, 'RUSTDESK_PUBLIC_HOST', 'rd.justplay.vn')


RUSTDESK_MENU_KEY = 'rustdesk'


def _can_connect(user) -> bool:
    """Ai được xem menu RustDesk thì được kết nối remote."""
    return user_can_access_menu(user, MODULE_AUDIT, RUSTDESK_MENU_KEY)


def _can_edit(user) -> bool:
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

    online_map = get_peers_online_map(host.rustdesk_id for host in page_obj)
    wol_enabled = getattr(settings, 'RUSTDESK_WOL_ENABLED', True)
    for host in page_obj:
        host.rd_is_online = online_map.get(normalize_rustdesk_id(host.rustdesk_id), False)
        host.rd_password_copy = effective_rustdesk_password(host.rustdesk_password)
        host.rd_can_wake = wol_enabled and bool(host.effective_mac_address)

    return render(request, 'audit/rustdesk_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'q': q,
        'current_active': active,
        'filtered_count': filtered_count,
        'can_connect_rustdesk': _can_connect(request.user),
        'can_edit_rustdesk': _can_edit(request.user),
        'can_delete_rustdesk': _can_delete(request.user),
        'rustdesk_online_check': getattr(settings, 'RUSTDESK_ONLINE_CHECK_ENABLED', True),
        'rustdesk_online_poll_sec': getattr(settings, 'RUSTDESK_ONLINE_POLL_SEC', 5),
        'rustdesk_wol_enabled': getattr(settings, 'RUSTDESK_WOL_ENABLED', True),
    })


@module_perm_required(MODULE_AUDIT, 'view')
@require_GET
def rustdesk_online_status(request):
    raw_ids = list(request.GET.getlist('id'))
    if not raw_ids and request.GET.get('ids'):
        raw_ids = [part.strip() for part in request.GET.get('ids', '').split(',') if part.strip()]
    peer_ids = [normalize_rustdesk_id(value) for value in raw_ids]
    peer_ids = [value for value in peer_ids if value]
    force_refresh = request.GET.get('refresh') == '1'
    online_map = get_peers_online_map(peer_ids, force_refresh=force_refresh) if peer_ids else {}
    return JsonResponse({
        'status': 'ok',
        'online': {peer_id: bool(online_map.get(peer_id)) for peer_id in peer_ids},
    })


@module_perm_required(MODULE_AUDIT, 'view')
@require_POST
def rustdesk_sync_devices(request):
    if not _can_edit(request.user):
        return JsonResponse({'status': 'error', 'message': 'Không có quyền.'}, status=403)

    overwrite = request.POST.get('overwrite') == '1'
    result = sync_all_rustdesk_hosts_from_devices(overwrite_mac=overwrite)
    message = (
        f'Đã liên kết {result.linked} thiết bị, cập nhật MAC {result.mac_updated} máy.'
    )
    if result.missing_mac:
        message += f' {result.missing_mac} máy thiết bị IT chưa có MAC (cần quét lại).'
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'status': 'ok',
            'message': message,
            'linked': result.linked,
            'mac_updated': result.mac_updated,
            'skipped': result.skipped,
            'missing_mac': result.missing_mac,
        })
    messages.success(request, message)
    return redirect('audit:rustdesk_list')


@module_perm_required(MODULE_AUDIT, 'view')
@require_POST
def rustdesk_wake(request, pk):
    if not _can_edit(request.user):
        return JsonResponse({'status': 'error', 'message': 'Không có quyền.'}, status=403)
    if not getattr(settings, 'RUSTDESK_WOL_ENABLED', True):
        return JsonResponse({'status': 'error', 'message': 'Wake-on-LAN đã tắt.'}, status=403)

    host = get_object_or_404(RustDeskHost.objects.select_related('device'), pk=pk)
    mac = host.effective_mac_address
    if not mac:
        return JsonResponse({
            'status': 'error',
            'message': 'Chưa có địa chỉ MAC. Nhập MAC hoặc liên kết thiết bị IT.',
        }, status=400)

    try:
        broadcast, mode = dispatch_wake_on_lan(
            mac,
            ip_address=str(host.ip_address) if host.ip_address else None,
        )
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=400)
    except OSError as exc:
        return JsonResponse({
            'status': 'error',
            'message': f'Không gửi được Wake-on-LAN: {exc}',
        }, status=500)

    via = 'NAS relay' if mode == 'relay' else 'broadcast'
    return JsonResponse({
        'status': 'ok',
        'message': f'Đã gửi Wake-on-LAN tới {host.name} qua {via} ({broadcast}).',
        'broadcast': broadcast,
        'mode': mode,
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
