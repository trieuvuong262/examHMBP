import json
from datetime import date

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from pathlib import Path
from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from hrm.module_permissions import MODULE_EQUIPMENT, user_can_access_module, user_can_edit_module
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import DeviceForm, ReportIssueForm
from .models import Device, MaintenanceLog
from .services.wmi_scan import (
    apply_probe_payload_to_device,
    discover_device_from_ip,
    is_local_wmi_available,
    is_relay_scan_available,
    is_scan_available,
    is_wmi_scan_supported,
    parse_ip_range,
    scan_device_wmi,
    scan_unavailable_message,
    upsert_device_from_probe,
    wmi_unavailable_message,
)
from .services.scan_backend import is_agent_scan_available, relay_http_url
from .services.scan_relay_client import ScanRelayError, scan_lan_remote, scan_range_remote, scan_targets_remote


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_EQUIPMENT):
            messages.error(request, 'Bạn không có quyền truy cập module Quản lý thiết bị.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _edit_required(view_func):
    @_access_required
    def wrapper(request, *args, **kwargs):
        if not user_can_edit_module(request.user, MODULE_EQUIPMENT):
            messages.error(request, 'Bạn không có quyền chỉnh sửa thiết bị.')
            return redirect('equipment:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


def _subnav_context():
    return {}


@_access_required
def dashboard(request):
    total_devices = Device.objects.count()
    broken_devices = Device.objects.filter(status=Device.STATUS_BROKEN).count()
    maintenance_devices = Device.objects.filter(status=Device.STATUS_MAINTENANCE).count()
    active_devices = Device.objects.filter(status=Device.STATUS_ACTIVE).count()
    scrapped_devices = Device.objects.filter(status=Device.STATUS_SCRAPPED).count()
    total_cost = MaintenanceLog.objects.aggregate(total=Sum('cost'))['total'] or 0

    recent_issues = MaintenanceLog.objects.filter(
        is_resolved=False,
        device__status=Device.STATUS_BROKEN,
    ).select_related('device', 'device__usage_department').order_by('-created_at')[:5]

    monitoring_issues = MaintenanceLog.objects.filter(
        is_resolved=False,
        device__status=Device.STATUS_MAINTENANCE,
    ).select_related('device').order_by('expected_return_date')[:5]

    current_year = date.today().year
    monthly_costs = MaintenanceLog.objects.filter(created_at__year=current_year).annotate(
        month=ExtractMonth('created_at'),
    ).values('month').annotate(total=Sum('cost')).order_by('month')
    cost_data = [0] * 12
    for item in monthly_costs:
        month = item.get('month')
        total = item.get('total')
        if month and 1 <= month <= 12:
            cost_data[month - 1] = int(total or 0)

    top_depts = MaintenanceLog.objects.values('device__usage_department_text').annotate(
        count=Count('id'),
    ).order_by('-count')[:5]
    dept_labels = [d['device__usage_department_text'] or '—' for d in top_depts]
    dept_data = [d['count'] for d in top_depts]

    top_cats = MaintenanceLog.objects.values('device__category').annotate(
        count=Count('id'),
    ).order_by('-count')
    cat_map = dict(Device.CATEGORY_CHOICES)
    cat_labels = [cat_map.get(item['device__category'], item['device__category']) for item in top_cats]
    cat_data = [item['count'] for item in top_cats]

    top_cost_depts = MaintenanceLog.objects.values('device__usage_department_text').annotate(
        total=Sum('cost'),
    ).order_by('-total')[:5]
    dept_cost_labels = [d['device__usage_department_text'] or '—' for d in top_cost_depts]
    dept_cost_data = [int(d['total'] or 0) for d in top_cost_depts]

    return render(request, 'equipment/dashboard.html', {
        'today': date.today(),
        'total_devices': total_devices,
        'broken_devices': broken_devices,
        'maintenance_devices': maintenance_devices,
        'active_devices': active_devices,
        'scrapped_devices': scrapped_devices,
        'total_cost': total_cost,
        'recent_issues': recent_issues,
        'monitoring_issues': monitoring_issues,
        'cost_data_json': json.dumps(cost_data),
        'dept_labels_json': json.dumps(dept_labels, ensure_ascii=False),
        'dept_data_json': json.dumps(dept_data),
        'cat_labels_json': json.dumps(cat_labels, ensure_ascii=False),
        'cat_data_json': json.dumps(cat_data),
        'dept_cost_labels_json': json.dumps(dept_cost_labels, ensure_ascii=False),
        'dept_cost_data_json': json.dumps(dept_cost_data),
        **_subnav_context(),
    })


@_access_required
def device_list(request):
    search_query = get_search_query(request)
    qs = Device.objects.select_related('usage_department', 'assigned_user__profile')

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(model_number__icontains=q)
            | Q(hostname__icontains=q)
            | Q(ip_address__icontains=q)
            | Q(usage_department_text__icontains=q)
            | Q(assigned_user_text__icontains=q)
            | Q(usage_department__name__icontains=q)
        )

    managed_by = request.GET.get('managed_by')
    if managed_by:
        qs = qs.filter(managed_by=managed_by)

    categories = request.GET.getlist('category')
    if categories:
        qs = qs.filter(category__in=categories)

    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)

    usage_department = request.GET.get('usage_department')
    if usage_department:
        qs = qs.filter(
            Q(usage_department_text=usage_department)
            | Q(usage_department__name=usage_department)
        )

    usage_room = request.GET.get('usage_room', '').strip()
    if usage_room:
        qs = qs.filter(usage_room__icontains=usage_room)

    is_online = request.GET.get('is_online')
    if is_online == '1':
        qs = qs.filter(is_online=True)
    elif is_online == '0':
        qs = qs.filter(is_online=False)

    sort_by = request.GET.get('sort')
    if sort_by == 'price_asc':
        qs = qs.order_by('total_price')
    elif sort_by == 'price_desc':
        qs = qs.order_by('-total_price')
    else:
        qs = qs.order_by('-created_at')

    qs = apply_term_search(qs, search_query, 'name__icontains', 'serial_number__icontains')
    filtered_count = qs.count()
    page_obj, query_string = paginate_queryset(request, qs)

    existing_depts = (
        Device.objects.exclude(usage_department_text='')
        .values_list('usage_department_text', flat=True)
        .distinct()
        .order_by('usage_department_text')
    )

    return render(request, 'equipment/device_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'q': q,
        'total_count': Device.objects.count(),
        'filtered_count': filtered_count,
        'current_managed_by': managed_by,
        'current_categories': categories,
        'current_status': status,
        'current_usage_department': usage_department,
        'current_usage_room': usage_room,
        'current_sort': sort_by,
        'current_is_online': is_online,
        'existing_depts': existing_depts,
        'managed_choices': Device.MANAGED_CHOICES,
        'category_choices': Device.CATEGORY_CHOICES,
        'status_choices': Device.STATUS_CHOICES,
        'can_edit': user_can_edit_module(request.user, MODULE_EQUIPMENT),
        'scan_available': is_scan_available(),
        'scan_via_relay': is_relay_scan_available() and not is_local_wmi_available(),
        'agent_scan_mode': is_agent_scan_available() and not is_relay_scan_available() and not is_local_wmi_available(),
        'wmi_scan_available': is_scan_available(),
        'scan_default_user': getattr(settings, 'EQUIPMENT_SCAN_DEFAULT_USER', ''),
        'scan_default_start_ip': getattr(settings, 'EQUIPMENT_SCAN_DEFAULT_START_IP', ''),
        'scan_default_end_ip': getattr(settings, 'EQUIPMENT_SCAN_DEFAULT_END_IP', ''),
        **_subnav_context(),
    })


@_edit_required
def device_add(request):
    if request.method == 'POST':
        form = DeviceForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã thêm thiết bị mới.')
            return redirect('equipment:device_list')
    else:
        form = DeviceForm()
    return render(request, 'equipment/device_form.html', {
        'form': form,
        'is_edit': False,
        **_subnav_context(),
    })


@_edit_required
def device_edit(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    if request.method == 'POST':
        form = DeviceForm(request.POST, instance=device)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật thiết bị.')
            return redirect('equipment:device_detail_manage', device_id=device.id)
    else:
        form = DeviceForm(instance=device)
    return render(request, 'equipment/device_form.html', {
        'form': form,
        'device': device,
        'is_edit': True,
        **_subnav_context(),
    })


@require_http_methods(['GET', 'POST'])
def device_qr_public(request, device_id):
    """Trang công khai quét QR — báo hỏng tạo yêu cầu Hỗ trợ kỹ thuật."""
    device = get_object_or_404(Device, pk=device_id)
    latest_log = None
    if device.status in (Device.STATUS_BROKEN, Device.STATUS_MAINTENANCE):
        latest_log = device.logs.filter(is_resolved=False).order_by('-created_at').first()

    if request.method == 'POST':
        if not request.user.is_authenticated:
            login_url = reverse('login') + f'?next={request.path}'
            messages.info(request, 'Vui lòng đăng nhập để gửi yêu cầu hỗ trợ kỹ thuật.')
            return redirect(login_url)

        if device.status in (Device.STATUS_BROKEN, Device.STATUS_MAINTENANCE):
            messages.warning(request, 'Thiết bị đang được xử lý — vui lòng chờ IT hoàn tất.')
            return redirect('equipment:device_qr_public', device_id=device.id)

        form = ReportIssueForm(request.POST)
        if form.is_valid():
            from service_requests.workflow_it import create_it_repair_request, get_it_repair_request_type

            request_type = get_it_repair_request_type()
            if not request_type:
                messages.error(request, 'Hệ thống chưa cấu hình loại yêu cầu Hỗ trợ kỹ thuật.')
                return redirect('equipment:device_qr_public', device_id=device.id)

            location = device.usage_room or device.usage_department_label
            title = f'Báo hỏng: {device.name}'
            service_request = create_it_repair_request(
                requester=request.user,
                request_type=request_type,
                title=title,
                description=form.cleaned_data['issue_description'],
                incident_category=form.cleaned_data['incident_category'],
                priority=form.cleaned_data['priority'],
                location_text=location,
                equipment_label=device.name,
                equipment_serial=device.serial_number or '',
                blocks_work=form.cleaned_data.get('blocks_work', False),
                equipment=device,
            )
            profile = getattr(request.user, 'profile', None)
            reporter_name = profile.full_name if profile and profile.full_name else request.user.username
            MaintenanceLog.objects.create(
                device=device,
                service_request=service_request,
                reported_by=reporter_name,
                reporter_email=request.user.email or '',
                issue_description=form.cleaned_data['issue_description'],
            )
            device.status = Device.STATUS_BROKEN
            device.save(update_fields=['status', 'updated_at'])

            from equipment.services.email_notify import notify_it_new_breakdown
            notify_it_new_breakdown(
                device=device,
                service_request=service_request,
                reporter_name=reporter_name,
                issue_description=form.cleaned_data['issue_description'],
            )

            messages.success(request, 'Đã gửi yêu cầu hỗ trợ kỹ thuật.')
            return redirect('service_requests:detail', pk=service_request.pk)
    else:
        form = ReportIssueForm(initial={'priority': 'normal'})

    return render(request, 'equipment/device_qr_public.html', {
        'device': device,
        'form': form,
        'latest_log': latest_log,
    })


@_access_required
def device_detail_manage(request, device_id):
    device = get_object_or_404(
        Device.objects.select_related('usage_department', 'assigned_user__profile'),
        pk=device_id,
    )
    logs = device.logs.select_related('service_request').order_by('-created_at')[:10]
    return render(request, 'equipment/device_detail_manage.html', {
        'device': device,
        'logs': logs,
        'can_edit': user_can_edit_module(request.user, MODULE_EQUIPMENT),
        **_subnav_context(),
    })


@_access_required
def device_history(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    logs = device.logs.select_related('service_request').order_by('-created_at')
    return render(request, 'equipment/device_history.html', {
        'device': device,
        'logs': logs,
        **_subnav_context(),
    })


@_access_required
def export_devices(request):
    if not user_can_edit_module(request.user, MODULE_EQUIPMENT):
        messages.error(request, 'Bạn không có quyền xuất dữ liệu.')
        return redirect('equipment:device_list')

    rows = Device.objects.all().values(
        'name', 'managed_by', 'category', 'status',
        'usage_department_text', 'usage_room', 'assigned_user_text', 'contact_email',
        'handover_date', 'model_number', 'serial_number', 'configuration', 'description',
        'hostname', 'ip_address', 'is_online', 'quantity', 'unit_price', 'total_price',
    )
    df = pd.DataFrame(list(rows))
    if not df.empty and 'is_online' in df.columns:
        df['is_online'] = df['is_online'].apply(lambda x: 'Online' if x else 'Offline')
    if not df.empty and 'handover_date' in df.columns:
        df['handover_date'] = df['handover_date'].astype(str).replace('NaT', '')

    rename_map = {
        'name': 'Tên thiết bị',
        'managed_by': 'Bộ phận QL',
        'category': 'Loại',
        'status': 'Trạng thái',
        'usage_department_text': 'Phòng ban sử dụng',
        'usage_room': 'Phòng / vị trí',
        'assigned_user_text': 'Người dùng',
        'contact_email': 'Email liên hệ',
        'handover_date': 'Ngày bàn giao',
        'model_number': 'Model',
        'serial_number': 'Serial Number',
        'configuration': 'Cấu hình',
        'description': 'Mô tả',
        'hostname': 'Hostname',
        'ip_address': 'Địa chỉ IP',
        'is_online': 'Trạng thái mạng',
        'quantity': 'Số lượng',
        'unit_price': 'Đơn giá',
        'total_price': 'Thành tiền',
    }
    df.rename(columns=rename_map, inplace=True)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=danh_sach_thiet_bi_justplay.xlsx'
    df.to_excel(response, index=False)
    return response


@_edit_required
def download_sample(request):
    sample = {
        'name': ['Máy tính Dell OptiPlex 3080'],
        'managed_by': ['IT'],
        'category': ['PC'],
        'status': ['active'],
        'usage_department_text': ['Phòng Sản xuất'],
        'usage_room': ['Line 2'],
        'assigned_user_text': ['Nguyễn Văn A'],
        'contact_email': ['user@justplay.vn'],
        'handover_date': ['2025-01-15'],
        'model_number': ['Dell-3080-SFF'],
        'serial_number': ['CN-0X1234'],
        'configuration': ['Core i5, RAM 16GB, SSD 512GB'],
        'description': ['Máy cấp mới đợt 1'],
        'hostname': ['PC-SX-01'],
        'ip_address': ['192.168.1.15'],
        'is_online': ['Online'],
        'quantity': [1],
        'unit_price': [15000000],
    }
    df = pd.DataFrame(sample)
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=file_mau_thiet_bi_justplay.xlsx'
    df.to_excel(response, index=False)
    return response


def _parse_excel_date(value):
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if hasattr(value, 'date'):
        return value.date()
    text = str(value).strip()
    if not text or text.lower() == 'nat':
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            from datetime import datetime
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


@_edit_required
@require_http_methods(['GET', 'POST'])
def import_devices(request):
    if request.method == 'GET':
        return render(request, 'equipment/import.html', _subnav_context())

    excel_file = request.FILES.get('excel_file')
    if not excel_file:
        messages.error(request, 'Vui lòng chọn file Excel.')
        return redirect('equipment:import_devices')

    try:
        df = pd.read_excel(excel_file)
        df = df.replace({pd.NA: None})
        count = 0
        for _, row in df.iterrows():
            name = row.get('name') or row.get('Tên thiết bị')
            if not name or (isinstance(name, float) and pd.isna(name)):
                continue
            handover_raw = row.get('handover_date') or row.get('Ngày bàn giao')
            Device.objects.create(
                name=str(name).strip(),
                managed_by=row.get('managed_by') or row.get('Bộ phận QL') or Device.MANAGED_IT,
                category=row.get('category') or row.get('Loại') or 'PC',
                status=row.get('status') or row.get('Trạng thái') or Device.STATUS_NEW,
                usage_department_text=str(
                    row.get('usage_department_text')
                    or row.get('usage_department')
                    or row.get('Phòng ban sử dụng')
                    or ''
                ),
                usage_room=str(row.get('usage_room') or row.get('Phòng / vị trí') or ''),
                assigned_user_text=str(
                    row.get('assigned_user_text') or row.get('user') or row.get('Người dùng') or ''
                ),
                contact_email=row.get('contact_email') or row.get('Email liên hệ') or '',
                handover_date=_parse_excel_date(handover_raw),
                model_number=str(row.get('model_number') or row.get('Model') or ''),
                serial_number=str(row.get('serial_number') or row.get('Serial Number') or ''),
                configuration=str(row.get('configuration') or row.get('Cấu hình') or ''),
                description=str(row.get('description') or row.get('Mô tả') or ''),
                hostname=str(row.get('hostname') or row.get('Hostname') or ''),
                ip_address=row.get('ip_address') or row.get('Địa chỉ IP') or None,
                quantity=int(row.get('quantity') or row.get('Số lượng') or 1),
                unit_price=int(row.get('unit_price') or row.get('Đơn giá') or 0),
            )
            count += 1
        messages.success(request, f'Đã nhập {count} thiết bị.')
    except Exception as exc:
        messages.error(request, f'Lỗi đọc file: {exc}')
    return redirect('equipment:device_list')


@_edit_required
@require_http_methods(['POST'])
def delete_bulk_devices(request):
    device_ids = request.POST.getlist('device_ids')
    if not device_ids:
        messages.warning(request, 'Vui lòng chọn ít nhất một thiết bị để xóa.')
        return redirect('equipment:device_list')

    qs = Device.objects.filter(id__in=device_ids)
    num = qs.count()
    qs.delete()
    messages.success(request, f'Đã xóa {num} thiết bị.')
    return redirect('equipment:device_list')


def _require_scan(request):
    if not is_scan_available():
        messages.error(request, scan_unavailable_message())
        return False
    return True


def _save_probes_to_db(probes: list[dict]) -> tuple[int, int]:
    found_count = 0
    new_device_count = 0
    for probe in probes:
        device, created = upsert_device_from_probe(probe)
        if device is None:
            continue
        found_count += 1
        if created:
            new_device_count += 1
    return found_count, new_device_count


@_edit_required
@require_http_methods(['POST'])
def scan_lan_network(request):
    """Quét toàn mạng LAN (/24) — qua Tailscale tới máy Windows IT."""
    if not _require_scan(request):
        return redirect('equipment:device_list')

    scan_user = (request.POST.get('scan_user') or '').strip()
    scan_pass = request.POST.get('scan_pass') or ''
    if not scan_user or not scan_pass:
        messages.error(request, 'Vui lòng nhập tài khoản và mật khẩu Admin domain.')
        return redirect('equipment:device_list')

    try:
        if is_local_wmi_available():
            from equipment.relay.wmi_standalone import detect_lan_ip_range, scan_ip_list

            start_ip, end_ip, lan_label = detect_lan_ip_range()
            ips = parse_ip_range(start_ip, end_ip)
            probes = scan_ip_list(ips, username=scan_user, password=scan_pass)
        else:
            data = scan_lan_remote(scan_user=scan_user, scan_pass=scan_pass)
            probes = data.get('probes', [])
            start_ip = data.get('start_ip', '')
            end_ip = data.get('end_ip', '')
            lan_label = data.get('lan_label') or f'{start_ip} – {end_ip}'
    except ScanRelayError as exc:
        messages.error(request, str(exc))
        return redirect('equipment:device_list')
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('equipment:device_list')

    found_count, new_device_count = _save_probes_to_db(probes)
    messages.success(
        request,
        f'Đã quét toàn LAN {lan_label}. '
        f'Tìm thấy {found_count} máy. Thêm mới {new_device_count} thiết bị.',
    )
    return redirect('equipment:device_list')


@_edit_required
@require_http_methods(['POST'])
def scan_selected_devices(request):
    if not _require_scan(request):
        return redirect('equipment:device_list')

    device_ids = request.POST.getlist('device_ids')
    scan_user = (request.POST.get('scan_user') or '').strip()
    scan_pass = request.POST.get('scan_pass') or ''

    if not device_ids:
        messages.warning(request, 'Chưa chọn thiết bị nào.')
        return redirect('equipment:device_list')
    if not scan_user or not scan_pass:
        messages.error(request, 'Vui lòng nhập tài khoản và mật khẩu Admin để quét WMI.')
        return redirect('equipment:device_list')

    devices = list(Device.objects.filter(id__in=device_ids))
    count_ip = 0
    count_wmi = 0
    count_qr = 0

    if is_local_wmi_available():
        for device in devices:
            ip_updated, wmi_updated, qr_redrawn = scan_device_wmi(
                device,
                username=scan_user,
                password=scan_pass,
            )
            if ip_updated:
                count_ip += 1
            if wmi_updated:
                count_wmi += 1
            if qr_redrawn:
                count_qr += 1
    else:
        try:
            targets = [
                {
                    'id': str(d.id),
                    'hostname': d.hostname or '',
                    'ip_address': str(d.ip_address) if d.ip_address else '',
                }
                for d in devices
            ]
            data = scan_targets_remote(targets=targets, scan_user=scan_user, scan_pass=scan_pass)
            device_map = {str(d.id): d for d in devices}
            for entry in data.get('results', []):
                device = device_map.get(entry.get('id'))
                if not device:
                    continue
                ip_u, wmi_u, qr_u = apply_probe_payload_to_device(device, entry)
                if ip_u:
                    count_ip += 1
                if wmi_u:
                    count_wmi += 1
                if qr_u:
                    count_qr += 1
        except ScanRelayError as exc:
            messages.error(request, str(exc))
            return redirect('equipment:device_list')

    messages.success(
        request,
        f'Hoàn tất quét {len(devices)} thiết bị. '
        f'Cập nhật IP: {count_ip}. WMI: {count_wmi}. Vẽ lại tem QR: {count_qr}.',
    )
    return redirect('equipment:device_list')


@_edit_required
@require_http_methods(['POST'])
def scan_network_range(request):
    if not _require_scan(request):
        return redirect('equipment:device_list')

    start_ip = (request.POST.get('start_ip') or '').strip()
    end_ip = (request.POST.get('end_ip') or '').strip()
    scan_user = (request.POST.get('scan_user') or '').strip()
    scan_pass = request.POST.get('scan_pass') or ''

    if not scan_user or not scan_pass:
        messages.error(request, 'Vui lòng nhập tài khoản và mật khẩu Admin.')
        return redirect('equipment:device_list')

    try:
        ip_list = parse_ip_range(start_ip, end_ip)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('equipment:device_list')

    found_count = 0
    new_device_count = 0

    if is_local_wmi_available():
        for ip_str in ip_list:
            try:
                result = discover_device_from_ip(ip_str, username=scan_user, password=scan_pass)
                if result:
                    found_count += 1
                    _, created = result
                    if created:
                        new_device_count += 1
            except Exception:
                continue
    else:
        try:
            data = scan_range_remote(
                start_ip=start_ip,
                end_ip=end_ip,
                scan_user=scan_user,
                scan_pass=scan_pass,
            )
            found_count, new_device_count = _save_probes_to_db(data.get('probes', []))
        except ScanRelayError as exc:
            messages.error(request, str(exc))
            return redirect('equipment:device_list')

    messages.success(
        request,
        f'Đã quét dải {start_ip} – {end_ip}. '
        f'Tìm thấy {found_count} máy. Thêm mới {new_device_count} thiết bị.',
    )
    return redirect('equipment:device_list')


@csrf_exempt
def api_agent_report(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Chỉ nhận POST'}, status=405)

    try:
        data = json.loads(request.body)
        secret = getattr(settings, 'EQUIPMENT_AGENT_SECRET', '')
        if not secret or data.get('api_secret') != secret:
            return JsonResponse({'status': 'error', 'message': 'Sai Secret Key'}, status=403)

        serial = data.get('serial')
        from equipment.services.wmi_scan import is_bad_serial

        if is_bad_serial(serial):
            return JsonResponse({'status': 'error', 'message': 'Serial không hợp lệ'}, status=400)

        device, created = Device.objects.get_or_create(
            serial_number=serial,
            defaults={
                'name': data.get('hostname') or f'PC-{serial[-6:]}',
                'status': Device.STATUS_ACTIVE,
            },
        )
        device.hostname = data.get('hostname') or device.hostname
        device.ip_address = data.get('ip') or device.ip_address
        device.model_number = data.get('model') or device.model_number
        device.configuration = (
            f"CPU: {data.get('cpu', '—')}\n"
            f"RAM: {data.get('ram', '—')} GB\n"
            f"Disk: {data.get('disk', '—')}"
        )
        device.is_online = True
        device.last_scan_date = timezone.now()
        device.save()

        from equipment.services.agent_install import link_user_from_agent_report

        link_user_from_agent_report(data=data, device=device)

        return JsonResponse({'status': 'success', 'created': created, 'device_id': str(device.id)})
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)


@csrf_exempt
def api_agent_poll(request):
    """Agent poll — có yêu cầu quét mới từ portal không."""
    secret = request.GET.get('api_secret', '')
    expected = getattr(settings, 'EQUIPMENT_AGENT_SECRET', '')
    if not expected or secret != expected:
        return JsonResponse({'status': 'error', 'message': 'Sai Secret Key'}, status=403)

    from equipment.models import EquipmentScanControl

    rescan_at = EquipmentScanControl.get_rescan_at()
    return JsonResponse({
        'status': 'ok',
        'rescan_at': rescan_at.isoformat() if rescan_at else None,
    })


@_edit_required
@require_http_methods(['POST'])
def request_agent_rescan(request):
    """Portal: yêu cầu mọi agent báo cáo lại (trong ~1–2 phút)."""
    from equipment.models import EquipmentScanControl
    from equipment.services.scan_backend import is_agent_scan_available

    if not is_agent_scan_available():
        messages.error(request, 'Chưa cấu hình EQUIPMENT_AGENT_SECRET trên server.')
        return redirect('equipment:device_list')

    when = EquipmentScanControl.request_agent_rescan()
    messages.success(
        request,
        f'Đã gửi tín hiệu quét tới các PC có Agent (lúc {when:%H:%M:%S}). '
        f'PC online sẽ cập nhật trong 1–2 phút — tải lại trang.',
    )
    return redirect('equipment:device_list')


@login_required
def agent_install_gate(request):
    """Màn hình bắt buộc cài agent — không thể vào module khác."""
    from equipment.services.agent_install import (
        agent_gate_enabled,
        agent_install_enabled,
        is_agent_install_required,
        user_is_in_equipment_registry,
    )

    if not agent_gate_enabled():
        return redirect('home_portal')
    if user_is_in_equipment_registry(request.user):
        return redirect('home_portal')
    if not is_agent_install_required(request):
        return redirect('home_portal')

    return render(request, 'equipment/agent_install_gate.html', {
        'portal_user': request.user,
        'agent_download_ready': agent_install_enabled(),
    })


@login_required
def agent_download_installer(request):
    """1 file .cmd cá nhân hóa — tải EXE, tạo ini, quét sau 5 giây."""
    from equipment.services.agent_install import (
        agent_install_enabled,
        build_installer_cmd,
        create_install_token,
    )

    if not agent_install_enabled():
        messages.error(request, 'Chưa bật Agent trên server (EQUIPMENT_AGENT_SECRET).')
        return redirect('home_portal')

    token = create_install_token(request.user)
    content = build_installer_cmd(user=request.user, token=token.token)
    filename = f'JustPlay-CaiDat-{request.user.username}.cmd'
    response = HttpResponse(content, content_type='application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _agent_exe_path() -> Path | None:
    custom = getattr(settings, 'EQUIPMENT_AGENT_EXE_PATH', '').strip()
    if custom:
        path = Path(custom)
        if path.is_file():
            return path
    base = Path(settings.BASE_DIR)
    for candidate in (
        base / 'static' / 'equipment' / 'JustPlayAgent.exe',
        base / 'dist' / 'JustPlayAgent.exe',
    ):
        if candidate.is_file():
            return candidate
    return None


def agent_serve_exe(request):
    """Agent EXE — curl từ file cài .cmd (không cần đăng nhập)."""
    path = _agent_exe_path()
    if not path:
        return HttpResponse('JustPlayAgent.exe chua duoc dat tren server.', status=404)
    with path.open('rb') as fh:
        data = fh.read()
    response = HttpResponse(data, content_type='application/octet-stream')
    response['Content-Disposition'] = 'attachment; filename="JustPlayAgent.exe"'
    return response


@login_required
def agent_install_done(request):
    """Trang xác nhận sau cài — chờ agent gửi thông tin lên quản lý thiết bị."""
    from equipment.services.agent_install import user_is_in_equipment_registry

    token_str = request.GET.get('token', '').strip()
    ready = user_is_in_equipment_registry(request.user)
    serial = ''

    if ready:
        from equipment.models import UserAgentRegistration

        reg = (
            UserAgentRegistration.objects.filter(user=request.user)
            .order_by('-registered_at')
            .first()
        )
        if reg:
            serial = reg.serial_number

    return render(request, 'equipment/agent_install_done.html', {
        'token': token_str,
        'ready': ready,
        'serial': serial,
    })


@login_required
def api_agent_install_status(request):
    """Poll — user đã có trong quản lý thiết bị chưa."""
    from equipment.services.agent_install import user_is_in_equipment_registry

    if user_is_in_equipment_registry(request.user):
        return JsonResponse({'ready': True, 'registered': True})

    return JsonResponse({'ready': False})


@require_GET
def agent_config_ping(request):
    """Ping cấu hình gate — kiểm tra production."""
    from equipment.services.agent_install import agent_gate_enabled, agent_install_enabled

    return JsonResponse({
        'gate_enabled': agent_gate_enabled(),
        'agent_secret_set': agent_install_enabled(),
        'exempt_usernames': getattr(settings, 'EQUIPMENT_AGENT_GATE_EXEMPT_USERNAMES', 'admin'),
        'middleware': 'equipment.middleware.AgentInstallGateMiddleware' in settings.MIDDLEWARE,
    })


@_edit_required
def agent_guide(request):
    portal_url = getattr(settings, 'PORTAL_PUBLIC_BASE_URL', '').rstrip('/')
    return render(request, 'equipment/agent_guide.html', {
        'portal_url': portal_url,
        'has_agent_secret': bool(getattr(settings, 'EQUIPMENT_AGENT_SECRET', '')),
        **_subnav_context(),
    })


@_edit_required
def scan_relay_guide(request):
    """Hướng dẫn quét WMI tập trung (relay Tailscale — tuỳ chọn)."""
    return render(request, 'equipment/scan_relay.html', {
        'relay_http_url': relay_http_url(),
        'has_relay_secret': bool(getattr(settings, 'EQUIPMENT_RELAY_SECRET', '')),
        'scan_available': is_scan_available(),
        **_subnav_context(),
    })
