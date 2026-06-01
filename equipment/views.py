import json
from datetime import date

import pandas as pd
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.db.models.functions import ExtractMonth
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from hrm.module_permissions import MODULE_EQUIPMENT, user_can_access_module, user_can_edit_module
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from .forms import DeviceForm, ReportIssueForm
from .models import Device, MaintenanceLog


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
    total_cost = MaintenanceLog.objects.aggregate(total=Sum('cost'))['total'] or 0

    recent_issues = MaintenanceLog.objects.filter(
        is_resolved=False,
        device__status=Device.STATUS_BROKEN,
    ).select_related('device').order_by('-created_at')[:5]

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

    return render(request, 'equipment/dashboard.html', {
        'total_devices': total_devices,
        'broken_devices': broken_devices,
        'maintenance_devices': maintenance_devices,
        'active_devices': active_devices,
        'total_cost': total_cost,
        'recent_issues': recent_issues,
        'cost_data': cost_data,
        'dept_labels': [d['device__usage_department_text'] or '—' for d in top_depts],
        'dept_data': [d['count'] for d in top_depts],
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
        )

    managed_by = request.GET.get('managed_by')
    if managed_by:
        qs = qs.filter(managed_by=managed_by)

    category = request.GET.get('category')
    if category:
        qs = qs.filter(category=category)

    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)

    qs = apply_term_search(qs, search_query, 'name__icontains', 'serial_number__icontains')
    page_obj, query_string = paginate_queryset(request, qs)

    return render(request, 'equipment/device_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'total_count': Device.objects.count(),
        'filtered_count': qs.count(),
        'current_managed_by': managed_by,
        'current_category': category,
        'current_status': status,
        'managed_choices': Device.MANAGED_CHOICES,
        'category_choices': Device.CATEGORY_CHOICES,
        'status_choices': Device.STATUS_CHOICES,
        'can_edit': user_can_edit_module(request.user, MODULE_EQUIPMENT),
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

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=danh_sach_thiet_bi_justplay.xlsx'
    df.to_excel(response, index=False)
    return response


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
            name = row.get('name')
            if not name or (isinstance(name, float) and pd.isna(name)):
                continue
            Device.objects.create(
                name=str(name).strip(),
                managed_by=row.get('managed_by') or Device.MANAGED_IT,
                category=row.get('category') or 'PC',
                status=row.get('status') or Device.STATUS_NEW,
                usage_department_text=str(row.get('usage_department_text') or row.get('usage_department') or ''),
                usage_room=str(row.get('usage_room') or ''),
                assigned_user_text=str(row.get('assigned_user_text') or row.get('user') or ''),
                contact_email=row.get('contact_email') or '',
                model_number=str(row.get('model_number') or ''),
                serial_number=str(row.get('serial_number') or ''),
                configuration=str(row.get('configuration') or ''),
                description=str(row.get('description') or ''),
                hostname=str(row.get('hostname') or ''),
                ip_address=row.get('ip_address') or None,
                quantity=int(row.get('quantity') or 1),
                unit_price=int(row.get('unit_price') or 0),
            )
            count += 1
        messages.success(request, f'Đã nhập {count} thiết bị.')
    except Exception as exc:
        messages.error(request, f'Lỗi đọc file: {exc}')
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
        if not serial or serial in ('Default string', 'None', ''):
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

        return JsonResponse({'status': 'success', 'created': created, 'device_id': str(device.id)})
    except Exception as exc:
        return JsonResponse({'status': 'error', 'message': str(exc)}, status=500)
