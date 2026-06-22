import json
from datetime import date

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
from django.views.decorators.http import require_GET, require_http_methods

from hrm.models import Department
from hrm.menu_permissions import (
    user_can_create_menu,
    user_can_delete_menu,
    user_can_edit_menu,
    user_can_export_menu,
    user_can_update_menu,
)
from hrm.module_permissions import (
    MODULE_EQUIPMENT,
    user_can_access_module,
    user_can_create_module,
    user_can_delete_module,
    user_can_edit_module,
    user_can_export_module,
    user_can_update_module,
)
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from equipment.categories import CATEGORY_GROUP_LABELS, import_columns_for_category
from equipment.services.device_categories import (
    categories_by_group,
    category_choices,
    category_map,
    valid_codes,
)
from equipment.services.device_statuses import status_choices

from .forms import DeviceForm, ReportIssueForm
from .models import Device, MaintenanceLog
from .scope import (
    SCOPE_IT,
    SCOPE_PRODUCTION,
    SCOPE_SHORT_LABELS,
    filter_devices_for_scope,
    it_repair_detail_url,
    merge_scope_context,
    scope_for_device,
    scope_urls,
)
from .services.import_export import (
    apply_device_list_filters,
    build_export_filename,
    build_sample_dataframe,
    export_devices_excel,
    import_devices_from_excel,
)


def _access_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not user_can_access_module(request.user, MODULE_EQUIPMENT):
            messages.error(request, 'Bạn không có quyền truy cập module Quản lý thiết bị.')
            return redirect('home_portal')
        return view_func(request, *args, **kwargs)
    return wrapper


def _equipment_menu_key(request) -> str | None:
    path = request.path
    if '/thiet-bi/san-xuat' in path:
        return 'production'
    if '/thiet-bi/it' in path:
        return 'it'
    return None


def _equipment_action_allowed(user, request, action: str) -> bool:
    menu_key = _equipment_menu_key(request)
    if menu_key:
        checker = {
            'create': user_can_create_menu,
            'update': user_can_update_menu,
            'delete': user_can_delete_menu,
            'export': user_can_export_menu,
            'edit': user_can_edit_menu,
        }.get(action, user_can_edit_menu)
        return checker(user, MODULE_EQUIPMENT, menu_key)
    module_checker = {
        'create': user_can_create_module,
        'update': user_can_update_module,
        'delete': user_can_delete_module,
        'export': user_can_export_module,
        'edit': user_can_edit_module,
    }.get(action, user_can_edit_module)
    return module_checker(user, MODULE_EQUIPMENT)


def _perm_required(action: str, *, redirect_name: str = 'equipment:dashboard_it'):
    def decorator(view_func):
        @_access_required
        def wrapper(request, *args, **kwargs):
            if not _equipment_action_allowed(request.user, request, action):
                messages.error(request, 'Bạn không có quyền thực hiện thao tác này trên module thiết bị.')
                return redirect(redirect_name)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


_create_required = _perm_required('create')
_update_required = _perm_required('update')
_delete_required = _perm_required('delete')
_export_required = _perm_required('export')
_edit_required = _perm_required('edit')


def _redirect_it_repair_list(equipment_scope=None):
    return redirect(scope_urls(equipment_scope or SCOPE_IT)['it_repair_list'])


def _subnav_context(request=None, equipment_scope=None, device=None):
    ctx = {}
    if request and request.user.is_authenticated:
        from equipment.services.it_repair_queue import pending_it_repair_steps_for_user
        ctx['can_edit_equipment'] = user_can_edit_module(request.user, MODULE_EQUIPMENT)
        ctx['can_export_equipment'] = user_can_export_module(request.user, MODULE_EQUIPMENT)
    else:
        ctx['can_edit_equipment'] = False
        ctx['can_export_equipment'] = False
    ctx.update(merge_scope_context(request, equipment_scope, device))
    if request and request.user.is_authenticated:
        from equipment.services.it_repair_queue import pending_it_repair_steps_for_user
        ctx['it_repair_pending_count'] = pending_it_repair_steps_for_user(
            request.user,
            ctx.get('equipment_scope'),
        ).count()
    else:
        ctx['it_repair_pending_count'] = 0
    return ctx


def _redirect_device_list(equipment_scope=None):
    return redirect(scope_urls(equipment_scope or SCOPE_IT)['device_list'])


def _redirect_import_hub(equipment_scope=None, category=''):
    url = scope_urls(equipment_scope or SCOPE_IT)['import_export_hub']
    if category:
        url = f'{url}?category={category}'
    return redirect(url)


@_access_required
def dashboard(request, equipment_scope=SCOPE_IT):
    device_qs = filter_devices_for_scope(Device.objects.all(), equipment_scope)
    total_devices = device_qs.count()
    broken_devices = device_qs.filter(status=Device.STATUS_BROKEN).count()
    maintenance_devices = device_qs.filter(status=Device.STATUS_MAINTENANCE).count()
    active_devices = device_qs.filter(status=Device.STATUS_ACTIVE).count()
    scrapped_devices = device_qs.filter(status=Device.STATUS_SCRAPPED).count()

    log_qs = MaintenanceLog.objects.filter(device__in=device_qs)
    total_cost = log_qs.aggregate(total=Sum('cost'))['total'] or 0

    recent_issues = log_qs.filter(
        is_resolved=False,
        device__status=Device.STATUS_BROKEN,
    ).select_related('device', 'device__usage_department').order_by('-created_at')[:5]

    monitoring_issues = log_qs.filter(
        is_resolved=False,
        device__status=Device.STATUS_MAINTENANCE,
    ).select_related('device').order_by('expected_return_date')[:5]

    current_year = date.today().year
    monthly_costs = log_qs.filter(created_at__year=current_year).annotate(
        month=ExtractMonth('created_at'),
    ).values('month').annotate(total=Sum('cost')).order_by('month')
    cost_data = [0] * 12
    for item in monthly_costs:
        month = item.get('month')
        total = item.get('total')
        if month and 1 <= month <= 12:
            cost_data[month - 1] = int(total or 0)

    top_depts = log_qs.values('device__usage_department_text').annotate(
        count=Count('id'),
    ).order_by('-count')[:5]
    dept_labels = [d['device__usage_department_text'] or '—' for d in top_depts]
    dept_data = [d['count'] for d in top_depts]

    top_cats = log_qs.values('device__category').annotate(
        count=Count('id'),
    ).order_by('-count')
    cat_map = category_map()
    cat_labels = [cat_map.get(item['device__category'], item['device__category']) for item in top_cats]
    cat_data = [item['count'] for item in top_cats]

    top_cost_depts = log_qs.values('device__usage_department_text').annotate(
        total=Sum('cost'),
    ).order_by('-total')[:5]
    dept_cost_labels = [d['device__usage_department_text'] or '—' for d in top_cost_depts]
    dept_cost_data = [int(d['total'] or 0) for d in top_cost_depts]

    asset_value = device_qs.aggregate(total=Sum('total_price'))['total'] or 0

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
        'asset_value': asset_value,
        **_subnav_context(request, equipment_scope),
    })


@_access_required
def it_repair_list(request, equipment_scope=SCOPE_IT):
    """Hàng đợi Hỗ trợ kỹ thuật — IT xử lý trong module thiết bị."""
    from equipment.services.it_repair_queue import pending_it_repair_steps_for_user

    search_query = get_search_query(request)
    qs = pending_it_repair_steps_for_user(request.user, equipment_scope)
    if search_query:
        qs = qs.filter(
            Q(request__title__icontains=search_query)
            | Q(request__description__icontains=search_query)
            | Q(request__requester__username__icontains=search_query)
            | Q(request__requester__profile__full_name__icontains=search_query)
            | Q(request__equipment_label__icontains=search_query)
            | Q(request__location_text__icontains=search_query)
        )
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'equipment/it_repair_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        **_subnav_context(request, equipment_scope),
    })


@_access_required
def legacy_it_repair_detail(request, pk):
    from service_requests.models import ServiceRequest

    service_request = get_object_or_404(
        ServiceRequest.objects.select_related('equipment'),
        pk=pk,
    )
    scope = scope_for_device(service_request.equipment if service_request.equipment_id else None)
    return redirect(it_repair_detail_url(scope, pk))


@_access_required
def it_repair_detail(request, pk, equipment_scope=SCOPE_IT):
    """Xử lý một yêu cầu Hỗ trợ kỹ thuật."""
    from equipment.services.it_repair_queue import (
        can_claim_it_repair_step,
        can_handle_it_repair_step,
    )
    from service_requests.forms import ItRepairCompleteForm
    from service_requests.models import ServiceRequest, ServiceRequestAttachment, ServiceRequestStep
    from service_requests.workflow import claim_step
    from service_requests.workflow_it import complete_it_repair_step
    from tasks.attachment_utils import read_separate_uploads

    service_request = get_object_or_404(
        ServiceRequest.objects.select_related(
            'requester', 'requester__profile', 'request_type', 'equipment',
        ).prefetch_related('steps', 'attachments', 'logs__actor__profile'),
        pk=pk,
    )
    if not service_request.is_it_repair:
        messages.error(request, 'Yêu cầu không thuộc loại Hỗ trợ kỹ thuật.')
        return _redirect_it_repair_list(equipment_scope)

    req_scope = service_request.effective_repair_equipment_scope()
    if equipment_scope and req_scope != equipment_scope:
        messages.error(
            request,
            f'Yêu cầu thuộc hàng đợi {SCOPE_SHORT_LABELS.get(req_scope, req_scope)}, '
            f'không phải {SCOPE_SHORT_LABELS.get(equipment_scope, equipment_scope)}.',
        )
        return _redirect_it_repair_list(equipment_scope)

    current_step = service_request.current_step
    if not current_step or current_step.step_code != ServiceRequestStep.STEP_IT_REPAIR:
        messages.info(request, 'Yêu cầu không còn ở bước IT xử lý.')
        return redirect('service_requests:detail', pk=pk)

    can_handle = can_handle_it_repair_step(request.user, current_step)
    can_claim = can_claim_it_repair_step(request.user, current_step)
    if not can_handle and not can_claim:
        messages.error(request, 'Bạn không có quyền xử lý yêu cầu này.')
        return _redirect_it_repair_list(equipment_scope)

    it_repair_form = ItRepairCompleteForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'claim' and can_claim:
                claim_step(current_step, actor=request.user)
                messages.success(request, 'Đã tiếp nhận yêu cầu.')
                return redirect(it_repair_detail_url(equipment_scope, pk))

            if action == 'complete_it_repair' and can_handle:
                it_repair_form = ItRepairCompleteForm(request.POST)
                if it_repair_form.is_valid():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    prepared = read_separate_uploads(
                        request.FILES.getlist('images'),
                        request.FILES.getlist('files'),
                    )
                    complete_it_repair_step(
                        current_step,
                        actor=request.user,
                        note=it_repair_form.cleaned_data['note'].strip(),
                        repair_cost=it_repair_form.cleaned_data.get('repair_cost'),
                        expected_return_date=it_repair_form.cleaned_data.get('expected_return_date'),
                    )
                    if prepared:
                        for original_name, content_file in prepared:
                            ServiceRequestAttachment.objects.create(
                                request=service_request,
                                step=current_step,
                                file=content_file,
                                original_name=original_name,
                                uploaded_by=request.user,
                                stage=ServiceRequestAttachment.STAGE_RESULT,
                            )
                    from equipment.services.email_notify import notify_repair_completed
                    notify_repair_completed(
                        service_request=service_request,
                        repair_note=it_repair_form.cleaned_data['note'].strip(),
                        repaired_by=request.user.get_full_name() or request.user.username,
                    )
                    messages.success(request, 'Đã hoàn thành xử lý — yêu cầu đã đóng.')
                    return _redirect_it_repair_list(equipment_scope)
        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(it_repair_detail_url(equipment_scope, pk))

    return render(request, 'equipment/it_repair_detail.html', {
        'service_request': service_request,
        'current_step': current_step,
        'can_handle': can_handle,
        'can_claim': can_claim,
        'it_repair_form': it_repair_form,
        'logs': service_request.logs.all()[:20],
        **_subnav_context(request, equipment_scope),
    })


@_access_required
def device_list(request, equipment_scope=SCOPE_IT):
    from equipment.services.scope_ui import categories_by_group_for_scope

    search_query = get_search_query(request)
    qs = filter_devices_for_scope(
        Device.objects.select_related('usage_department', 'assigned_user__profile'),
        equipment_scope,
    )
    scope_total_qs = filter_devices_for_scope(Device.objects.all(), equipment_scope)

    q = request.GET.get('q', '').strip()
    if q:
        qs = qs.filter(
            Q(name__icontains=q)
            | Q(device_code__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(model_number__icontains=q)
            | Q(hostname__icontains=q)
            | Q(ip_address__icontains=q)
            | Q(rustdesk_id__icontains=q)
            | Q(usage_department_text__icontains=q)
            | Q(assigned_user_text__icontains=q)
            | Q(usage_department__name__icontains=q)
            | Q(usage_room__icontains=q)
        )

    managed_department = request.GET.get('managed_department')
    if managed_department:
        qs = qs.filter(managed_department_id=managed_department)

    categories = request.GET.getlist('category')
    category = (request.GET.get('category') or '').strip()
    if category and not categories:
        categories = [category]
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
        qs = qs.filter(usage_room=usage_room)

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

    existing_depts = _equipment_departments()
    existing_usage_rooms = _equipment_usage_rooms(equipment_scope)

    return render(request, 'equipment/device_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'q': q,
        'total_count': scope_total_qs.count(),
        'filtered_count': filtered_count,
        'stat_active': scope_total_qs.filter(status=Device.STATUS_ACTIVE).count(),
        'stat_broken': scope_total_qs.filter(status=Device.STATUS_BROKEN).count(),
        'stat_maintenance': scope_total_qs.filter(status=Device.STATUS_MAINTENANCE).count(),
        'current_managed_department': managed_department,
        'current_category': category,
        'current_categories': categories,
        'current_status': status,
        'current_usage_department': usage_department,
        'current_usage_room': usage_room,
        'current_sort': sort_by,
        'existing_depts': existing_depts,
        'existing_usage_rooms': existing_usage_rooms,
        'managed_departments': Department.objects.filter(is_active=True).order_by('sort_order', 'name'),
        'category_choices': category_choices(),
        'category_groups': categories_by_group_for_scope(equipment_scope),
        'status_choices': status_choices(),
        'can_edit': user_can_edit_module(request.user, MODULE_EQUIPMENT),
        'can_edit_equipment': user_can_edit_module(request.user, MODULE_EQUIPMENT),
        'can_export': user_can_export_module(request.user, MODULE_EQUIPMENT),
        'show_device_list_toolbar': True,
        **_subnav_context(request, equipment_scope),
    })


@_create_required
def device_add(request, equipment_scope=SCOPE_IT):
    from equipment.services.managed_department import default_managed_department_for_scope

    if request.method == 'POST':
        form = DeviceForm(
            request.POST, request.FILES,
            equipment_scope=equipment_scope,
            editor_user=request.user,
        )
        if form.is_valid():
            device = form.save(commit=False)
            if not form.cleaned_data.get('managed_department'):
                device.managed_department = default_managed_department_for_scope(equipment_scope)
            device.save()
            from equipment.services.device_update_log import log_device_created

            log_device_created(device, request.user)
            messages.success(request, 'Đã thêm thiết bị mới.')
            return _redirect_device_list(equipment_scope)
    else:
        form = DeviceForm(equipment_scope=equipment_scope, editor_user=request.user)
    return render(request, 'equipment/device_form.html', {
        'form': form,
        'is_edit': False,
        'is_it_device': equipment_scope == SCOPE_IT,
        **_subnav_context(request, equipment_scope),
    })


@_update_required
@require_http_methods(['GET', 'POST'])
def device_edit(request, device_id):
    if request.method == 'GET':
        return redirect('equipment:device_detail_manage', device_id=device_id)
    return device_detail_manage(request, device_id)


def _get_device_by_key(device_key):
    from uuid import UUID

    try:
        UUID(str(device_key))
    except (ValueError, AttributeError, TypeError):
        return get_object_or_404(Device, device_code__iexact=str(device_key))
    return get_object_or_404(Device, pk=device_key)


@require_http_methods(['GET', 'POST'])
def device_qr_public(request, device_key):
    """Trang công khai quét QR — báo hỏng tạo yêu cầu Hỗ trợ kỹ thuật."""
    device = _get_device_by_key(device_key)
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
            return redirect('equipment:device_qr_public', device_key=device.device_code)

        from equipment.scope import scope_for_device

        device_scope = scope_for_device(device)
        form = ReportIssueForm(request.POST, repair_equipment_scope=device_scope)
        if form.is_valid():
            from service_requests.workflow_it import create_it_repair_request, get_it_repair_request_type

            request_type = get_it_repair_request_type()
            if not request_type:
                messages.error(request, 'Hệ thống chưa cấu hình loại yêu cầu Hỗ trợ kỹ thuật.')
                return redirect('equipment:device_qr_public', device_key=device.device_code)

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
                equipment_label=f'{device.device_code} — {device.name}',
                equipment_serial=device.serial_number or '',
                blocks_work=form.cleaned_data.get('blocks_work', False),
                equipment=device,
                repair_equipment_scope=device_scope,
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
        from equipment.scope import scope_for_device

        form = ReportIssueForm(
            initial={'priority': 'normal'},
            repair_equipment_scope=scope_for_device(device),
        )

    return render(request, 'equipment/device_qr_public.html', {
        'device': device,
        'form': form,
        'latest_log': latest_log,
    })


@_access_required
@require_http_methods(['GET', 'POST'])
def device_detail_manage(request, device_id):
    device = get_object_or_404(
        Device.objects.select_related(
            'managed_department',
            'usage_department',
            'assigned_user__profile',
            'assigned_user__profile__department',
        ),
        pk=device_id,
    )
    from equipment.services.shared_pc import get_registered_users

    can_edit = user_can_update_module(request.user, MODULE_EQUIPMENT)
    form = None

    if request.method == 'POST':
        if not can_edit:
            messages.error(request, 'Bạn không có quyền sửa thiết bị.')
            return redirect('equipment:device_detail_manage', device_id=device.id)
        form = DeviceForm(
            request.POST, request.FILES,
            instance=device,
            equipment_scope=merge_scope_context(request, device=device).get('equipment_scope'),
            editor_user=request.user,
        )
        if form.is_valid():
            from equipment.services.device_update_log import log_device_update

            before = Device.objects.select_related(
                'managed_department',
                'usage_department',
                'assigned_user__profile',
            ).get(pk=device.pk)
            form.save()
            after = Device.objects.select_related(
                'managed_department',
                'usage_department',
                'assigned_user__profile',
            ).get(pk=device.pk)
            log_device_update(before, after, request.user)
            messages.success(request, 'Đã cập nhật thiết bị và tạo lại tem QR.')
            return redirect('equipment:device_detail_manage', device_id=device.id)
    elif can_edit:
        scope_ctx = merge_scope_context(request, device=device)
        form = DeviceForm(
            instance=device,
            equipment_scope=scope_ctx.get('equipment_scope'),
            editor_user=request.user,
        )

    logs = device.logs.select_related('service_request').order_by('-created_at')[:10]
    shared_users = list(get_registered_users(device)) if device.is_shared_pc else []
    scope_ctx = merge_scope_context(request, device=device)
    return render(request, 'equipment/device_detail_manage.html', {
        'device': device,
        'form': form,
        'shared_users': shared_users,
        'logs': logs,
        'can_edit': can_edit,
        'is_it_device': device.is_it_equipment,
        **scope_ctx,
    })


@_access_required
def device_history(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    logs = device.logs.select_related('service_request').order_by('-created_at')
    return render(request, 'equipment/device_history.html', {
        'device': device,
        'logs': logs,
        'history_tab': 'incident',
        **_subnav_context(request, device=device),
    })


@_access_required
def device_update_history(request, device_id):
    device = get_object_or_404(Device, pk=device_id)
    logs = device.update_logs.select_related('changed_by').order_by('-created_at')
    return render(request, 'equipment/device_update_history.html', {
        'device': device,
        'logs': logs,
        'history_tab': 'update',
        **_subnav_context(request, device=device),
    })


def _equipment_departments():
    return (
        Device.objects.exclude(usage_department_text='')
        .values_list('usage_department_text', flat=True)
        .distinct()
        .order_by('usage_department_text')
    )


def _equipment_usage_rooms(equipment_scope):
    from equipment.scope import SCOPE_PRODUCTION
    from equipment.production_locations import production_usage_room_filter_choices

    if equipment_scope == SCOPE_PRODUCTION:
        return production_usage_room_filter_choices()
    qs = filter_devices_for_scope(Device.objects.all(), equipment_scope)
    return (
        qs.exclude(usage_room='')
        .values_list('usage_room', flat=True)
        .distinct()
        .order_by('usage_room')
    )


def _import_export_context(request, equipment_scope=SCOPE_IT):
    from equipment.services.scope_ui import categories_by_group_for_scope

    default_category = 'PC' if equipment_scope == SCOPE_IT else 'SEW_LOCKSTITCH'
    selected_category = (request.GET.get('category') or default_category).strip()
    if selected_category not in valid_codes():
        selected_category = default_category
    cmap = category_map()

    user = request.user
    return {
        'can_edit': user_can_edit_module(user, MODULE_EQUIPMENT),
        'can_create': user_can_create_module(user, MODULE_EQUIPMENT),
        'can_export': user_can_export_module(user, MODULE_EQUIPMENT),
        'category_groups': categories_by_group_for_scope(equipment_scope),
        'selected_category': selected_category,
        'selected_category_label': cmap.get(selected_category, selected_category),
        'import_columns': import_columns_for_category(selected_category),
        **_subnav_context(request, equipment_scope),
    }


@_access_required
def import_export_hub(request, equipment_scope=SCOPE_IT):
    """Trang nhập Excel theo loại thiết bị."""
    return render(request, 'equipment/import_export.html', _import_export_context(request, equipment_scope))


@_export_required
def export_devices(request, equipment_scope=SCOPE_IT):
    if request.method == 'POST':
        params = request.POST
    else:
        params = request.GET

    base_qs = filter_devices_for_scope(
        Device.objects.select_related('usage_department', 'assigned_user__profile'),
        equipment_scope,
    )
    qs = apply_device_list_filters(base_qs, params)
    count = qs.count()
    if count == 0:
        messages.warning(request, 'Không có thiết bị nào để xuất (theo bộ lọc hiện tại).')
        return _redirect_device_list(equipment_scope)

    categories = params.getlist('category') if hasattr(params, 'getlist') else []
    buffer = export_devices_excel(qs, equipment_scope=equipment_scope)
    filename = build_export_filename(count, equipment_scope, categories or None)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@_create_required
def download_sample(request, equipment_scope=SCOPE_IT):
    default_category = 'PC' if equipment_scope == SCOPE_IT else 'SEW_LOCKSTITCH'
    category = (request.GET.get('category') or default_category).strip()
    if category not in valid_codes():
        messages.error(request, 'Loại thiết bị không hợp lệ.')
        return _redirect_import_hub(equipment_scope)

    df = build_sample_dataframe(category)
    label = category_map().get(category, category).replace('/', '-')
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="mau_{category}_{label[:30]}.xlsx"'
    df.to_excel(response, index=False)
    return response


@_create_required
@require_http_methods(['GET', 'POST'])
def import_devices(request, equipment_scope=SCOPE_IT):
    default_category = 'PC' if equipment_scope == SCOPE_IT else 'SEW_LOCKSTITCH'
    if request.method == 'GET':
        category = (request.GET.get('category') or default_category).strip()
        return _redirect_import_hub(equipment_scope, category)

    selected_category = (request.POST.get('category') or default_category).strip()
    if selected_category not in valid_codes():
        selected_category = default_category

    excel_file = request.FILES.get('excel_file')
    category = (request.POST.get('category') or selected_category).strip()
    if not excel_file:
        messages.error(request, 'Vui lòng chọn file Excel.')
        return _redirect_import_hub(equipment_scope, category)
    if category not in valid_codes():
        messages.error(request, 'Loại thiết bị không hợp lệ.')
        return _redirect_import_hub(equipment_scope)

    try:
        count, errors = import_devices_from_excel(excel_file, category)
        if count:
            messages.success(
                request,
                f'Đã nhập {count} thiết bị loại «{category_map().get(category, category)}».',
            )
        if errors:
            preview = '; '.join(errors[:5])
            if len(errors) > 5:
                preview += f' … (+{len(errors) - 5} lỗi)'
            messages.warning(request, f'Một số dòng bị bỏ qua: {preview}')
        if not count and not errors:
            messages.warning(request, 'Không có dòng dữ liệu hợp lệ trong file.')
    except Exception as exc:
        messages.error(request, f'Lỗi đọc file: {exc}')
        return _redirect_import_hub(equipment_scope, category)

    return _redirect_device_list(equipment_scope)


def _redirect_category_list(equipment_scope=None):
    return redirect(scope_urls(equipment_scope or SCOPE_IT)['category_list'])


@_access_required
def category_list(request, equipment_scope=SCOPE_IT):
    from equipment.models import DeviceCategory
    from equipment.services.scope_ui import is_it_scope

    search = (request.GET.get('q') or '').strip()
    profile = 'it' if is_it_scope(equipment_scope) else 'machine'
    qs = DeviceCategory.objects.filter(import_profile=profile)
    if search:
        qs = qs.filter(
            Q(code__icontains=search) | Q(name__icontains=search) | Q(group__icontains=search)
        )
    categories = qs.order_by('group', 'sort_order', 'name')
    return render(request, 'equipment/category_list.html', {
        'categories': categories,
        'search_query': search,
        'group_labels': CATEGORY_GROUP_LABELS,
        **_subnav_context(request, equipment_scope),
    })


@_create_required
@require_http_methods(['GET', 'POST'])
def category_add(request, equipment_scope=SCOPE_IT):
    from equipment.forms import DeviceCategoryForm

    if request.method == 'POST':
        form = DeviceCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã thêm loại «{form.instance.name}».')
            return _redirect_category_list(equipment_scope)
    else:
        from equipment.models import DeviceCategory
        from equipment.services.scope_ui import is_it_scope

        profile = DeviceCategory.IMPORT_IT if is_it_scope(equipment_scope) else DeviceCategory.IMPORT_MACHINE
        form = DeviceCategoryForm(initial={'import_profile': profile})
    return render(request, 'equipment/category_form.html', {
        'form': form,
        'is_edit': False,
        **_subnav_context(request, equipment_scope),
    })


@_update_required
@require_http_methods(['GET', 'POST'])
def category_edit(request, pk, equipment_scope=SCOPE_IT):
    from equipment.forms import DeviceCategoryForm
    from equipment.models import DeviceCategory

    category = get_object_or_404(DeviceCategory, pk=pk)
    if request.method == 'POST':
        form = DeviceCategoryForm(request.POST, instance=category)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật loại thiết bị.')
            return _redirect_category_list(equipment_scope)
    else:
        form = DeviceCategoryForm(instance=category)
    return render(request, 'equipment/category_form.html', {
        'form': form,
        'category': category,
        'is_edit': True,
        **_subnav_context(request, equipment_scope),
    })


@_delete_required
@require_http_methods(['POST'])
def category_delete(request, pk, equipment_scope=SCOPE_IT):
    from equipment.models import Device, DeviceCategory

    category = get_object_or_404(DeviceCategory, pk=pk)
    in_use = Device.objects.filter(category=category.code).count()
    if in_use:
        messages.error(request, f'Không xóa được — còn {in_use} thiết bị đang dùng loại này.')
        return _redirect_category_list(equipment_scope)
    name = category.name
    category.delete()
    messages.success(request, f'Đã xóa loại «{name}».')
    return _redirect_category_list(equipment_scope)


def _redirect_status_list(equipment_scope=None):
    return redirect(scope_urls(equipment_scope or SCOPE_IT)['status_list'])


@_access_required
def status_list(request, equipment_scope=SCOPE_IT):
    from equipment.models import DeviceStatus

    search = (request.GET.get('q') or '').strip()
    qs = DeviceStatus.objects.all()
    if search:
        qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))
    statuses = qs.order_by('sort_order', 'name')
    return render(request, 'equipment/status_list.html', {
        'statuses': statuses,
        'search_query': search,
        **_subnav_context(request, equipment_scope),
    })


@_create_required
@require_http_methods(['GET', 'POST'])
def status_add(request, equipment_scope=SCOPE_IT):
    from equipment.forms import DeviceStatusForm

    if request.method == 'POST':
        form = DeviceStatusForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f'Đã thêm trạng thái «{form.instance.name}».')
            return _redirect_status_list(equipment_scope)
    else:
        form = DeviceStatusForm()
    return render(request, 'equipment/status_form.html', {
        'form': form,
        'is_edit': False,
        **_subnav_context(request, equipment_scope),
    })


@_update_required
@require_http_methods(['GET', 'POST'])
def status_edit(request, pk, equipment_scope=SCOPE_IT):
    from equipment.forms import DeviceStatusForm
    from equipment.models import DeviceStatus

    status = get_object_or_404(DeviceStatus, pk=pk)
    if request.method == 'POST':
        form = DeviceStatusForm(request.POST, instance=status)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật trạng thái.')
            return _redirect_status_list(equipment_scope)
    else:
        form = DeviceStatusForm(instance=status)
    return render(request, 'equipment/status_form.html', {
        'form': form,
        'status': status,
        'is_edit': True,
        **_subnav_context(request, equipment_scope),
    })


@_delete_required
@require_http_methods(['POST'])
def status_delete(request, pk, equipment_scope=SCOPE_IT):
    from equipment.models import Device, DeviceStatus

    status = get_object_or_404(DeviceStatus, pk=pk)
    if status.is_system:
        messages.error(request, 'Không xóa được trạng thái hệ thống.')
        return _redirect_status_list(equipment_scope)
    in_use = Device.objects.filter(status=status.code).count()
    if in_use:
        messages.error(request, f'Không xóa được — còn {in_use} thiết bị đang dùng trạng thái này.')
        return _redirect_status_list(equipment_scope)
    name = status.name
    status.delete()
    messages.success(request, f'Đã xóa trạng thái «{name}».')
    return _redirect_status_list(equipment_scope)


@_delete_required
@require_http_methods(['POST'])
def delete_bulk_devices(request, equipment_scope=SCOPE_IT):
    device_ids = request.POST.getlist('device_ids')
    if not device_ids:
        messages.warning(request, 'Vui lòng chọn ít nhất một thiết bị để xóa.')
        return _redirect_device_list(equipment_scope)

    qs = Device.objects.filter(id__in=device_ids)
    num = qs.count()
    qs.delete()
    messages.success(request, f'Đã xóa {num} thiết bị.')
    return _redirect_device_list(equipment_scope)


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
        from equipment.agent.core import is_bad_serial
        from equipment.services.agent_install import (
            MACHINE_TYPE_PERSONAL,
            link_user_from_agent_report,
            resolve_machine_type_from_report,
        )

        if is_bad_serial(serial):
            return JsonResponse({'status': 'error', 'message': 'Serial không hợp lệ'}, status=400)

        if resolve_machine_type_from_report(data) == MACHINE_TYPE_PERSONAL:
            return JsonResponse({
                'status': 'success',
                'personal': True,
                'skipped': True,
                'message': 'Máy cá nhân không còn đăng ký qua portal',
            })

        from equipment.services.agent_device import apply_agent_hardware_to_device
        from equipment.services.chassis_category import infer_it_category_from_agent_data
        from equipment.services.agent_device import agent_device_default_name
        from equipment.services.device_code import allocate_agent_device_code
        from equipment.services.managed_department import default_managed_department_for_scope
        from equipment.scope import SCOPE_IT

        inferred_category = infer_it_category_from_agent_data(data) or 'PC'
        it_dept = default_managed_department_for_scope(SCOPE_IT)
        device, created = Device.objects.get_or_create(
            serial_number=serial,
            defaults={
                'name': agent_device_default_name(data, serial),
                'device_code': allocate_agent_device_code(),
                'status': Device.STATUS_ACTIVE,
                'category': inferred_category,
                'managed_department': it_dept,
            },
        )

        hw_fields = apply_agent_hardware_to_device(device, data, created=created)
        device.save(update_fields=sorted(set(hw_fields)))

        link_user_from_agent_report(data=data, device=device)

        return JsonResponse({
            'status': 'success',
            'created': created,
            'device_id': str(device.id),
        })
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
