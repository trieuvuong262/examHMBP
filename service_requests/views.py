from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from django.db.models import Q

from .access import user_can_access_flow
from .flow import (
    FLOW_DE_XUAT,
    FLOW_HO_TRO,
    FLOW_LABELS,
    normalize_flow_tab,
)
from .forms import (
    DivisionHeadApproveForm,
    ItRepairCompleteForm,
    ItRepairCreateForm,
    LineItemFormSet,
    PurchaseCompleteForm,
    RecurringItemCatalogForm,
    RejectStepForm,
    RequesterConfirmForm,
    ServiceRequestCreateForm,
    StepActionForm,
)
from .models import (
    RecurringItemCatalog,
    RequestType,
    ServiceRequest,
    ServiceRequestAttachment,
    ServiceRequestStep,
)
from .permissions import (
    can_claim_step,
    can_handle_step,
    can_manage_recurring_catalog,
    can_view_pricing,
    can_view_request,
    get_goods_receiver_candidates,
    get_procurement_staff_candidates,
    pending_steps_for_user,
)
from .workflow import (
    approve_step,
    cancel_request,
    claim_step,
    complete_execution_step,
    complete_procurement_quote,
    complete_purchase_step,
    create_request_with_steps,
    get_active_request_type,
    log_action,
    reject_step,
)
from PortalJustPlay.list_search import apply_combined_search, apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset
from tasks.attachment_utils import read_separate_uploads
from .workflow_it import (
    create_it_repair_request,
    get_it_repair_request_type,
)


def _subnav_context(request, *, flow_tab=FLOW_DE_XUAT):
    return {'flow_tab': flow_tab}


def _filter_by_flow(qs, flow_tab):
    if flow_tab == FLOW_HO_TRO:
        return qs.filter(request_type__code=RequestType.CODE_IT_REPAIR)
    if flow_tab == FLOW_DE_XUAT:
        return qs.filter(request_type__code=RequestType.CODE_ASSET_PURCHASE)
    return qs


def _list_url_for_request(service_request):
    if service_request.is_it_repair:
        return reverse('service_requests:ho_tro_my')
    return reverse('service_requests:de_xuat_my')


def _detail_url(service_request):
    if service_request.is_it_repair:
        return reverse('service_requests:ho_tro_detail', kwargs={'pk': service_request.pk})
    return reverse('service_requests:de_xuat_detail', kwargs={'pk': service_request.pk})


def _flow_access_required(view_func=None, *, flow_tab=None):
    def decorator(fn):
        @login_required
        def wrapper(request, *args, **kwargs):
            ft = normalize_flow_tab(
                kwargs.get('flow_tab') or flow_tab or request.resolver_match.kwargs.get('flow_tab'),
            )
            if not user_can_access_flow(request.user, ft):
                messages.error(
                    request,
                    f'Bạn không có quyền truy cập module {FLOW_LABELS.get(ft, ft)}.',
                )
                return redirect('home_portal')
            return fn(request, *args, **kwargs)
        return wrapper
    if view_func is not None:
        return decorator(view_func)
    return decorator


def _catalog_required(view_func):
    @_flow_access_required(flow_tab=FLOW_DE_XUAT)
    def wrapper(request, *args, **kwargs):
        if not can_manage_recurring_catalog(request.user):
            messages.error(request, 'Chỉ Thu mua mới quản lý danh mục định kỳ.')
            return redirect('service_requests:de_xuat_my')
        return view_func(request, *args, **kwargs)
    return wrapper


def _save_attachments(request_obj, prepared_files, *, uploaded_by, stage, step=None):
    for original_name, content_file in prepared_files:
        ServiceRequestAttachment.objects.create(
            request=request_obj,
            step=step,
            file=content_file,
            original_name=original_name,
            uploaded_by=uploaded_by,
            stage=stage,
        )


def _parse_quote_submission(request, service_request):
    """Đọc POST: qty + danh sách NCC cho từng dòng hàng."""
    line_updates = {}
    for line in service_request.line_items.all():
        qty_key = f'line_{line.pk}_qty'
        qty_raw = request.POST.get(qty_key, '').strip()
        try:
            qty = Decimal(qty_raw) if qty_raw else None
        except InvalidOperation:
            qty = None

        quotes = []
        idx = 0
        while True:
            prefix = f'line_{line.pk}_quote_{idx}_'
            supplier = request.POST.get(f'{prefix}supplier', '').strip()
            price_raw = request.POST.get(f'{prefix}price', '').strip()
            selected = request.POST.get(f'{prefix}selected') == 'on'
            file_key = f'{prefix}file'
            if not supplier and not price_raw:
                break
            try:
                unit_price = Decimal(price_raw.replace(',', '')) if price_raw else None
            except InvalidOperation:
                unit_price = None
            quote_file = request.FILES.get(file_key)
            quotes.append({
                'supplier_name': supplier,
                'unit_price': unit_price,
                'is_selected': selected,
                'quote_file': quote_file,
            })
            idx += 1

        line_updates[line.pk] = {
            'quantity_confirmed': qty,
            'quotes': quotes,
        }
    return line_updates


def _line_items_from_formset(formset, recurring_item=None):
    items = []
    for form in formset:
        if not form.cleaned_data or form.cleaned_data.get('DELETE'):
            continue
        desc = (form.cleaned_data.get('description') or '').strip()
        if not desc:
            continue
        items.append({
            'description': desc,
            'quantity': form.cleaned_data['quantity'],
            'unit': form.cleaned_data['unit'],
            'recurring_item': recurring_item if len(items) == 0 and recurring_item else None,
        })
    return items


@login_required
def request_hub(request):
    from hrm.module_permissions import MODULE_DE_XUAT, MODULE_HO_TRO, user_can_access_module
    if user_can_access_module(request.user, MODULE_DE_XUAT):
        return redirect('service_requests:de_xuat_my')
    if user_can_access_module(request.user, MODULE_HO_TRO):
        return redirect('service_requests:ho_tro_my')
    messages.error(request, 'Bạn không có quyền truy cập module Yêu cầu.')
    return redirect('home_portal')


@_flow_access_required
def my_requests(request, flow_tab=None):
    search_query = get_search_query(request)
    flow_tab = normalize_flow_tab(flow_tab or request.GET.get('loai'))

    qs = ServiceRequest.objects.filter(
        requester=request.user,
    ).select_related('request_type').prefetch_related('steps')
    qs = _filter_by_flow(qs, flow_tab)
    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)
    qs = apply_term_search(
        qs, search_query,
        'title__icontains', 'description__icontains', 'request_type__name__icontains',
        'equipment_label__icontains', 'location_text__icontains',
    )
    page_obj, query_string = paginate_queryset(request, qs)
    ctx = _subnav_context(request, flow_tab=flow_tab)
    ctx.update({
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'current_status': status,
        'status_tabs': [
            ('', 'Tất cả'),
            (ServiceRequest.STATUS_IN_PROGRESS, 'Đang xử lý'),
            (ServiceRequest.STATUS_COMPLETED, 'Hoàn thành'),
            (ServiceRequest.STATUS_REJECTED, 'Từ chối'),
            (ServiceRequest.STATUS_CANCELLED, 'Đã hủy'),
        ],
    })
    return render(request, 'service_requests/my_list.html', ctx)


@_flow_access_required
def pending_requests(request, flow_tab=None):
    search_query = get_search_query(request)
    flow_tab = normalize_flow_tab(flow_tab or request.GET.get('loai'))

    qs = pending_steps_for_user(request.user)
    if flow_tab == FLOW_HO_TRO:
        qs = qs.filter(request__request_type__code=RequestType.CODE_IT_REPAIR)
    else:
        qs = qs.filter(request__request_type__code=RequestType.CODE_ASSET_PURCHASE)

    qs = apply_combined_search(qs, search_query, lambda term: (
        Q(request__title__icontains=term)
        | Q(request__description__icontains=term)
        | Q(name__icontains=term)
        | Q(request__requester__username__icontains=term)
        | Q(request__requester__profile__full_name__icontains=term)
        | Q(request__requester__profile__employee_code__icontains=term)
        | Q(request__equipment_label__icontains=term)
    ))
    page_obj, query_string = paginate_queryset(request, qs)
    ctx = _subnav_context(request, flow_tab=flow_tab)
    ctx.update({
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
    })
    return render(request, 'service_requests/pending_list.html', ctx)


@_flow_access_required(flow_tab=FLOW_DE_XUAT)
def create_request(request):
    request_type = get_active_request_type()
    if not request_type:
        messages.warning(request, 'Chưa cấu hình loại yêu cầu. Liên hệ quản trị viên.')
        return redirect('service_requests:my')

    if request.method == 'POST':
        form = ServiceRequestCreateForm(request.POST, request_type=request_type)
        line_formset = LineItemFormSet(request.POST, prefix='lines')
        if form.is_valid() and line_formset.is_valid():
            recurring_item = form.cleaned_data.get('recurring_item')
            line_items = _line_items_from_formset(line_formset, recurring_item)
            if not line_items and not recurring_item:
                messages.error(request, 'Vui lòng thêm ít nhất một dòng hàng.')
            else:
                try:
                    service_request = create_request_with_steps(
                        requester=request.user,
                        request_type=request_type,
                        title=form.cleaned_data['title'],
                        description=form.cleaned_data['description'],
                        line_items=line_items or None,
                        recurring_item=recurring_item,
                        needs_advance=form.cleaned_data.get('needs_advance', False),
                        advance_amount=form.cleaned_data.get('advance_amount'),
                    )
                    prepared = read_separate_uploads(
                        request.FILES.getlist('images'),
                        request.FILES.getlist('files'),
                    )
                    if prepared:
                        _save_attachments(
                            service_request,
                            prepared,
                            uploaded_by=request.user,
                            stage=ServiceRequestAttachment.STAGE_REQUEST,
                        )
                        log_action(
                            service_request,
                            actor=request.user,
                            action='attachment',
                            message=f'Đính kèm {len(prepared)} file',
                        )
                    messages.success(request, 'Đã gửi yêu cầu — đang chờ xử lý theo quy trình.')
                    return redirect(_detail_url(service_request))
                except ValueError as exc:
                    messages.error(request, str(exc))
    else:
        form = ServiceRequestCreateForm(request_type=request_type)
        line_formset = LineItemFormSet(prefix='lines')

    return render(request, 'service_requests/form.html', {
        'form': form,
        'line_formset': line_formset,
        'request_type': request_type,
        **_subnav_context(request, flow_tab=FLOW_DE_XUAT),
    })


def _resolve_it_repair_tab_scope(request, *, equipment_scope=None, linked_equipment=None):
    """Tab IT / sản xuất — POST > GET tab > thiết bị liên kết > mặc định IT."""
    from equipment.scope import SCOPE_PRODUCTION, normalize_repair_equipment_scope, scope_for_device

    if request.method == 'POST':
        raw = request.POST.get('repair_scope') or request.POST.get('tab')
        if raw:
            return normalize_repair_equipment_scope(raw)
    tab = (request.GET.get('tab') or '').strip().lower()
    if tab in ('production', 'san-xuat', 'san_xuat'):
        return SCOPE_PRODUCTION
    if tab == 'it':
        return normalize_repair_equipment_scope('it')
    if equipment_scope:
        return normalize_repair_equipment_scope(equipment_scope)
    if linked_equipment is not None:
        return scope_for_device(linked_equipment)
    return normalize_repair_equipment_scope('it')


@_flow_access_required(flow_tab=FLOW_HO_TRO)
def create_it_repair(request, equipment_scope=None):
    from equipment.scope import (
        SCOPE_IT,
        SCOPE_PRODUCTION,
        normalize_repair_equipment_scope,
        scope_context,
        scope_for_device,
    )

    request_type = get_it_repair_request_type()
    if not request_type:
        messages.warning(request, 'Chưa cấu hình loại yêu cầu Hỗ trợ kỹ thuật. Liên hệ quản trị viên.')
        return redirect('service_requests:ho_tro_my')

    profile = getattr(request.user, 'profile', None)
    default_location = ''
    if profile and profile.department_id:
        default_location = profile.department.name

    linked_equipment = None
    equipment_id = request.GET.get('equipment') or request.POST.get('equipment_id')
    if equipment_id:
        try:
            from equipment.models import Device
            linked_equipment = Device.objects.filter(pk=equipment_id).first()
        except Exception:
            linked_equipment = None

    repair_scope = _resolve_it_repair_tab_scope(
        request,
        equipment_scope=equipment_scope,
        linked_equipment=linked_equipment,
    )
    scope_ctx = scope_context(repair_scope)

    if linked_equipment and scope_for_device(linked_equipment) != repair_scope:
        repair_scope = scope_for_device(linked_equipment)
        scope_ctx = scope_context(repair_scope)

    if request.method == 'POST':
        form = ItRepairCreateForm(request.POST, request_type=request_type)
        if form.is_valid():
            try:
                service_request = create_it_repair_request(
                    requester=request.user,
                    request_type=request_type,
                    title=form.cleaned_data['title'],
                    description=form.cleaned_data['description'],
                    incident_category=form.cleaned_data['incident_category'],
                    priority=form.cleaned_data['priority'],
                    location_text=form.cleaned_data['location_text'],
                    equipment_label=form.cleaned_data.get('equipment_label', ''),
                    equipment_serial=form.cleaned_data.get('equipment_serial', ''),
                    blocks_work=form.cleaned_data.get('blocks_work', False),
                    equipment=linked_equipment,
                    repair_equipment_scope=repair_scope,
                )
                prepared = read_separate_uploads(
                    request.FILES.getlist('images'),
                    request.FILES.getlist('files'),
                )
                if prepared:
                    _save_attachments(
                        service_request,
                        prepared,
                        uploaded_by=request.user,
                        stage=ServiceRequestAttachment.STAGE_REQUEST,
                    )
                    log_action(
                        service_request,
                        actor=request.user,
                        action='attachment',
                        message=f'Đính kèm {len(prepared)} file',
                    )
                profile = getattr(request.user, 'profile', None)
                reporter_name = (
                    profile.full_name if profile and profile.full_name else request.user.username
                )
                from equipment.services.email_notify import notify_breakdown_from_request
                notify_breakdown_from_request(service_request, reporter_name=reporter_name)
                messages.success(request, 'Đã gửi yêu cầu hỗ trợ kỹ thuật — đang chờ xử lý.')
                return redirect(_detail_url(service_request))
            except ValueError as exc:
                messages.error(request, str(exc))
    else:
        initial = {
            'location_text': default_location,
            'priority': ServiceRequest.PRIORITY_NORMAL,
        }
        if linked_equipment:
            initial.update({
                'title': f'Báo hỏng: {linked_equipment.name}',
                'equipment_label': linked_equipment.name,
                'equipment_serial': linked_equipment.serial_number or '',
                'location_text': linked_equipment.usage_room or linked_equipment.usage_department_label or default_location,
            })
        form = ItRepairCreateForm(request_type=request_type, initial=initial)

    tab_it_active = repair_scope != SCOPE_PRODUCTION
    return render(request, 'service_requests/it_repair_form.html', {
        'form': form,
        'request_type': request_type,
        'linked_equipment': linked_equipment,
        'repair_scope': repair_scope,
        'is_production_repair': repair_scope == SCOPE_PRODUCTION,
        'tab_it_active': tab_it_active,
        'create_url_it': reverse('service_requests:create_it_repair') + '?tab=it',
        'create_url_production': reverse('service_requests:create_it_repair') + '?tab=production',
        **scope_ctx,
        **_subnav_context(request, flow_tab=FLOW_HO_TRO),
    })


@login_required
def request_detail_legacy(request, pk):
    service_request = get_object_or_404(ServiceRequest, pk=pk)
    return redirect(_detail_url(service_request))


@login_required
def request_detail(request, pk, flow_tab=None):
    service_request = get_object_or_404(
        ServiceRequest.objects.select_related(
            'requester', 'requester__profile', 'request_type', 'recurring_item', 'goods_receiver__profile',
        ).prefetch_related(
            'steps__assignee__profile',
            'steps__target_department',
            'attachments__uploaded_by',
            'logs__actor__profile',
            'logs__step',
            'line_items__quotes',
            'line_items__recurring_item',
        ),
        pk=pk,
    )
    if not can_view_request(request.user, service_request):
        messages.error(request, 'Bạn không có quyền xem yêu cầu này.')
        return redirect(_list_url_for_request(service_request))

    current_step = service_request.current_step
    can_handle_current = bool(current_step and can_handle_step(request.user, current_step))
    can_claim_current = bool(current_step and can_claim_step(request.user, current_step))
    show_pricing = (
        service_request.is_procurement
        and can_view_pricing(request.user, service_request)
    )

    action_form = StepActionForm()
    reject_form = RejectStepForm()
    division_head_form = DivisionHeadApproveForm(
        staff_queryset=get_procurement_staff_candidates(),
    )
    purchase_form = PurchaseCompleteForm(
        receiver_queryset=get_goods_receiver_candidates(service_request),
    )
    it_repair_form = ItRepairCompleteForm()
    requester_confirm_form = RequesterConfirmForm()

    flow_tab = normalize_flow_tab(
        flow_tab or (FLOW_HO_TRO if service_request.is_it_repair else FLOW_DE_XUAT),
    )
    if not user_can_access_flow(request.user, flow_tab):
        messages.error(
            request,
            f'Bạn không có quyền truy cập module {FLOW_LABELS.get(flow_tab, flow_tab)}.',
        )
        return redirect('home_portal')

    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'cancel' and service_request.requester_id == request.user.id:
                cancel_request(service_request, actor=request.user)
                messages.info(request, 'Đã hủy yêu cầu.')
                return redirect(_list_url_for_request(service_request))

            if not current_step:
                messages.error(request, 'Yêu cầu không còn bước đang xử lý.')
                return redirect(_detail_url(service_request))

            if action == 'claim' and can_claim_current:
                claim_step(current_step, actor=request.user)
                messages.success(request, 'Đã tiếp nhận yêu cầu.')
                return redirect(_detail_url(service_request))

            if action == 'submit_quote' and can_handle_current:
                if current_step.step_code != ServiceRequestStep.STEP_PROCUREMENT_QUOTE:
                    raise ValueError('Bước hiện tại không phải kiểm tra giá.')
                if not current_step.assignee_id:
                    claim_step(current_step, actor=request.user)
                    current_step.refresh_from_db()
                line_updates = _parse_quote_submission(request, service_request)
                note = request.POST.get('quote_note', '').strip()
                complete_procurement_quote(
                    current_step,
                    actor=request.user,
                    line_updates=line_updates,
                    note=note or 'Hoàn thành báo giá NCC',
                )
                messages.success(request, 'Đã hoàn thành báo giá — chuyển bước duyệt tiếp theo.')
                return redirect(_detail_url(service_request))

            if action == 'approve' and can_handle_current and current_step.is_approval:
                if current_step.step_code == ServiceRequestStep.STEP_DIVISION_HEAD:
                    division_head_form = DivisionHeadApproveForm(
                        request.POST,
                        staff_queryset=get_procurement_staff_candidates(),
                    )
                    if division_head_form.is_valid():
                        if not current_step.assignee_id:
                            claim_step(current_step, actor=request.user)
                            current_step.refresh_from_db()
                        approve_step(
                            current_step,
                            actor=request.user,
                            note=division_head_form.cleaned_data.get('note', ''),
                            procurement_assignee=division_head_form.cleaned_data['procurement_assignee'],
                        )
                        messages.success(request, 'Đã duyệt và chỉ định nhân viên Thu mua.')
                        return redirect(_detail_url(service_request))
                    messages.error(request, 'Vui lòng chọn nhân viên Thu mua xử lý.')
                else:
                    action_form = StepActionForm(request.POST)
                    if action_form.is_valid():
                        if not current_step.assignee_id:
                            claim_step(current_step, actor=request.user)
                            current_step.refresh_from_db()
                        approve_step(current_step, actor=request.user, note=action_form.cleaned_data.get('note', ''))
                        messages.success(request, 'Đã duyệt bước này.')
                        return redirect(_detail_url(service_request))

            if action == 'reject' and can_handle_current and current_step.is_approval:
                reject_form = RejectStepForm(request.POST)
                if reject_form.is_valid():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    reject_step(current_step, actor=request.user, reason=reject_form.cleaned_data['reason'])
                    messages.info(request, 'Đã từ chối yêu cầu.')
                    return redirect(_detail_url(service_request))

            if action == 'complete_purchase' and can_handle_current:
                if current_step.step_code != ServiceRequestStep.STEP_PURCHASE:
                    raise ValueError('Bước hiện tại không phải đặt hàng.')
                purchase_form = PurchaseCompleteForm(
                    request.POST,
                    receiver_queryset=get_goods_receiver_candidates(service_request),
                )
                if purchase_form.is_valid():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    complete_purchase_step(
                        current_step,
                        actor=request.user,
                        goods_receiver=purchase_form.cleaned_data['goods_receiver'],
                        note=purchase_form.cleaned_data['note'].strip(),
                    )
                    messages.success(request, 'Đã ghi nhận đặt hàng — chờ người nhận xác nhận.')
                    return redirect(_detail_url(service_request))

            if action == 'complete' and can_handle_current and current_step.is_execution:
                if service_request.is_it_repair:
                    raise ValueError('Dùng form xử lý IT cho yêu cầu sửa chữa.')
                action_form = StepActionForm(request.POST)
                if action_form.is_valid() and action_form.cleaned_data.get('note', '').strip():
                    if not current_step.assignee_id:
                        claim_step(current_step, actor=request.user)
                        current_step.refresh_from_db()
                    prepared = read_separate_uploads(
                        request.FILES.getlist('images'),
                        request.FILES.getlist('files'),
                    )
                    complete_execution_step(
                        current_step,
                        actor=request.user,
                        note=action_form.cleaned_data['note'].strip(),
                    )
                    if prepared:
                        _save_attachments(
                            service_request,
                            prepared,
                            uploaded_by=request.user,
                            stage=ServiceRequestAttachment.STAGE_RESULT,
                            step=current_step,
                        )
                    messages.success(request, 'Đã hoàn thành bước thực hiện.')
                    return redirect(_detail_url(service_request))
                messages.error(request, 'Vui lòng nhập kết quả xử lý.')

        except ValueError as exc:
            messages.error(request, str(exc))
            return redirect(_detail_url(service_request))

    first_active = service_request.steps.exclude(
        status=ServiceRequestStep.STATUS_SKIPPED,
    ).order_by('step_order').first()
    can_cancel = (
        service_request.requester_id == request.user.id
        and service_request.status == ServiceRequest.STATUS_IN_PROGRESS
        and first_active
        and first_active.status == ServiceRequestStep.STATUS_PENDING
    )

    equipment_it_url = ''
    if (
        service_request.is_it_repair
        and current_step
        and current_step.step_code == ServiceRequestStep.STEP_IT_REPAIR
    ):
        equipment_it_url = reverse('equipment:it_repair_detail', kwargs={'pk': service_request.pk})

    ctx = _subnav_context(request, flow_tab=flow_tab)
    ctx.update({
        'service_request': service_request,
        'steps': service_request.steps.all(),
        'line_items': service_request.line_items.all(),
        'logs': service_request.logs.all(),
        'request_attachments': service_request.attachments.filter(stage=ServiceRequestAttachment.STAGE_REQUEST),
        'current_step': current_step,
        'can_handle_current': can_handle_current,
        'can_claim_current': can_claim_current,
        'can_cancel': can_cancel,
        'show_pricing': show_pricing,
        'action_form': action_form,
        'reject_form': reject_form,
        'division_head_form': division_head_form,
        'purchase_form': purchase_form,
        'it_repair_form': it_repair_form,
        'requester_confirm_form': requester_confirm_form,
        'equipment_it_url': equipment_it_url,
        'list_url': _list_url_for_request(service_request),
    })
    return render(request, 'service_requests/detail.html', ctx)


@_catalog_required
def recurring_catalog_list(request):
    search_query = get_search_query(request)
    qs = RecurringItemCatalog.objects.all()
    qs = apply_term_search(qs, search_query, 'name__icontains', 'description__icontains')
    page_obj, query_string = paginate_queryset(request, qs)
    ctx = _subnav_context(request, flow_tab=FLOW_DE_XUAT)
    ctx.update({
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'can_manage_catalog': True,
    })
    return render(request, 'service_requests/catalog_list.html', ctx)


@_catalog_required
def recurring_catalog_create(request):
    if request.method == 'POST':
        form = RecurringItemCatalogForm(request.POST)
        if form.is_valid():
            item = form.save(commit=False)
            item.created_by = request.user
            item.save()
            messages.success(request, 'Đã thêm hàng vào danh mục định kỳ.')
            return redirect('service_requests:catalog_list')
    else:
        form = RecurringItemCatalogForm()
    return render(request, 'service_requests/catalog_form.html', {
        'form': form,
        'is_edit': False,
        **_subnav_context(request, flow_tab=FLOW_DE_XUAT),
    })


@_catalog_required
def recurring_catalog_edit(request, pk):
    item = get_object_or_404(RecurringItemCatalog, pk=pk)
    if request.method == 'POST':
        form = RecurringItemCatalogForm(request.POST, instance=item)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật danh mục.')
            return redirect('service_requests:catalog_list')
    else:
        form = RecurringItemCatalogForm(instance=item)
    return render(request, 'service_requests/catalog_form.html', {
        'form': form,
        'item': item,
        'is_edit': True,
        **_subnav_context(request, flow_tab=FLOW_DE_XUAT),
    })


@_catalog_required
def recurring_catalog_delete(request, pk):
    item = get_object_or_404(RecurringItemCatalog, pk=pk)
    if request.method == 'POST':
        item.is_active = False
        item.save(update_fields=['is_active', 'updated_at'])
        messages.info(request, 'Đã ẩn hàng khỏi danh mục.')
        return redirect('service_requests:catalog_list')
    return redirect('service_requests:catalog_list')
