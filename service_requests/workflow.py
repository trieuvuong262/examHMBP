"""Quy trình mua hàng — sinh bước động, báo giá NCC, duyệt theo giá trị."""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from hrm.permissions import (
    ROLE_DIRECTOR,
    ROLE_DIVISION_HEAD,
    ROLE_TEAM_LEADER,
    get_profile,
    is_director,
    is_division_head,
    is_team_leader,
)

from .models import (
    ProcurementLineItem,
    ProcurementSupplierQuote,
    RequestType,
    RequestTypeStepTemplate,
    ServiceRequest,
    ServiceRequestLog,
    ServiceRequestStep,
)

AMOUNT_ACCOUNTING_MIN = Decimal('2000000')
AMOUNT_DIRECTOR_MIN = Decimal('10000000')


def find_team_leader(user):
    if not user or not user.is_authenticated:
        return None
    return User.objects.filter(
        profile__subordinates=user,
        is_active=True,
        profile__is_employed=True,
        profile__role=ROLE_TEAM_LEADER,
    ).order_by('profile__full_name', 'username').first()


def find_division_head_manager(user):
    if not user or not user.is_authenticated:
        return None
    return User.objects.filter(
        profile__subordinates=user,
        is_active=True,
        profile__is_employed=True,
        profile__role=ROLE_DIVISION_HEAD,
    ).order_by('profile__full_name', 'username').first()


def find_director_user():
    return User.objects.filter(
        is_active=True,
        profile__is_employed=True,
        profile__role=ROLE_DIRECTOR,
    ).order_by('profile__full_name', 'username').first()


def department_has_team_leaders(department):
    if not department:
        return False
    return User.objects.filter(
        profile__department=department,
        profile__role=ROLE_TEAM_LEADER,
        profile__is_employed=True,
        is_active=True,
    ).exists()


def get_department_by_patterns(*patterns):
    from hrm.models import Department

    for pattern in patterns:
        dept = Department.objects.filter(name__icontains=pattern).first()
        if dept:
            return dept
    return None


def get_procurement_department():
    return get_department_by_patterns('thu mua', 'mua hàng', 'mua hang')


def get_accounting_department():
    return get_department_by_patterns('kế toán', 'ke toan', 'tài chính kế toán')


def _needs_team_leader_step(requester):
    profile = get_profile(requester)
    if not profile or not profile.department_id:
        return False
    if is_team_leader(requester) or is_division_head(requester) or is_director(requester):
        return False
    return department_has_team_leaders(profile.department)


def _needs_division_head_step(requester):
    return not is_division_head(requester) and not is_director(requester)


def _initial_step_status(depends_on_step, *, skipped=False):
    if skipped:
        return ServiceRequestStep.STATUS_SKIPPED
    if depends_on_step is None:
        return ServiceRequestStep.STATUS_PENDING
    if depends_on_step.status in {
        ServiceRequestStep.STATUS_COMPLETED,
        ServiceRequestStep.STATUS_SKIPPED,
    }:
        return ServiceRequestStep.STATUS_PENDING
    return ServiceRequestStep.STATUS_BLOCKED


def _resolve_assignee(assignee_rule, requester):
    if assignee_rule == RequestTypeStepTemplate.RULE_DIRECT_MANAGER:
        return find_division_head_manager(requester) or find_team_leader(requester)
    if assignee_rule == RequestTypeStepTemplate.RULE_DIRECTOR:
        return find_director_user()
    return None


def log_action(request_obj, *, actor, action, message='', step=None):
    ServiceRequestLog.objects.create(
        request=request_obj,
        step=step,
        actor=actor,
        action=action,
        message=message,
    )


def _create_step(
    service_request,
    *,
    step_order,
    step_code,
    name,
    step_kind,
    assignee_rule,
    target_department=None,
    assignee=None,
    depends_on=None,
    skipped=False,
):
    status = _initial_step_status(depends_on, skipped=skipped)
    if status == ServiceRequestStep.STATUS_PENDING and assignee is None:
        assignee = _resolve_assignee(assignee_rule, service_request.requester)

    return ServiceRequestStep.objects.create(
        request=service_request,
        step_order=step_order,
        step_code=step_code,
        name=name,
        step_kind=step_kind,
        assignee_rule=assignee_rule,
        target_department=target_department,
        assignee=assignee if status == ServiceRequestStep.STATUS_PENDING else None,
        depends_on=depends_on,
        status=status,
    )


def _build_initial_steps(service_request, requester):
    steps = []
    order = 1
    previous = None
    procurement_dept = get_procurement_department()

    if _needs_team_leader_step(requester):
        tl = find_team_leader(requester)
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_TEAM_LEADER,
            name='Tổ trưởng duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
            assignee=tl,
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1

    if _needs_division_head_step(requester):
        dh = find_division_head_manager(requester)
        step = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_DIVISION_HEAD,
            name='Trưởng bộ phận duyệt',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
            assignee=dh,
            depends_on=previous,
        )
        steps.append(step)
        previous = step
        order += 1

    quote_step = _create_step(
        service_request,
        step_order=order,
        step_code=ServiceRequestStep.STEP_PROCUREMENT_QUOTE,
        name='Thu mua kiểm tra giá & NCC',
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        target_department=procurement_dept,
        depends_on=previous,
    )
    steps.append(quote_step)
    return steps


def _remaining_steps(request_obj):
    return request_obj.steps.exclude(status__in=ServiceRequestStep.TERMINAL_STATUSES)


def _compute_selected_total(service_request):
    total = Decimal('0')
    for line in service_request.line_items.all():
        quote = line.selected_quote
        if not quote:
            raise ValueError(f'Dòng "{line.description}" chưa chọn nhà cung cấp.')
        total += quote.unit_price * line.effective_quantity
    return total


def _determine_approval_tier(service_request, total):
    if service_request.is_from_catalog or total < AMOUNT_ACCOUNTING_MIN:
        return ServiceRequest.TIER_NONE
    if total >= AMOUNT_DIRECTOR_MIN:
        return ServiceRequest.TIER_DIRECTOR
    return ServiceRequest.TIER_ACCOUNTANT


def _insert_post_quote_steps(service_request, *, after_step, actor):
    total = _compute_selected_total(service_request)
    tier = _determine_approval_tier(service_request, total)

    service_request.selected_total_amount = total
    service_request.approval_tier = tier
    service_request.save(update_fields=[
        'selected_total_amount', 'approval_tier', 'updated_at',
    ])

    order = service_request.steps.aggregate(m=Max('step_order'))['m'] or 0
    previous = after_step
    accounting_dept = get_accounting_department()
    procurement_dept = get_procurement_department()

    if tier == ServiceRequest.TIER_DIRECTOR:
        order += 1
        previous = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_DIRECTOR,
            name='Giám đốc duyệt chi phí',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DIRECTOR,
            depends_on=previous,
        )
    elif tier == ServiceRequest.TIER_ACCOUNTANT:
        order += 1
        previous = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_ACCOUNTANT,
            name='Kế toán duyệt chi phí',
            step_kind=RequestTypeStepTemplate.KIND_APPROVAL,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department=accounting_dept,
            depends_on=previous,
        )

    if service_request.needs_advance:
        order += 1
        previous = _create_step(
            service_request,
            step_order=order,
            step_code=ServiceRequestStep.STEP_ADVANCE,
            name='Tạm ứng (nếu có)',
            step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
            assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
            target_department=procurement_dept,
            depends_on=previous,
        )

    order += 1
    previous = _create_step(
        service_request,
        step_order=order,
        step_code=ServiceRequestStep.STEP_PURCHASE,
        name='Thu mua đặt hàng',
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        target_department=procurement_dept,
        depends_on=previous,
    )

    order += 1
    _create_step(
        service_request,
        step_order=order,
        step_code=ServiceRequestStep.STEP_RECEIPT,
        name='Xác nhận nhận hàng',
        step_kind=RequestTypeStepTemplate.KIND_EXECUTION,
        assignee_rule=RequestTypeStepTemplate.RULE_DIRECT_MANAGER,
        depends_on=previous,
    )

    log_action(
        service_request,
        actor=actor,
        action='quoted',
        message=f'Tổng NCC đã chọn: {total:,.0f} VNĐ · Cấp duyệt: {tier}',
        step=after_step,
    )

    unlocked = unlock_next_steps(after_step)
    for child in unlocked:
        _log_step_opened(service_request, actor, child)
    return service_request


def _log_step_opened(request_obj, actor, step):
    if step.assignee:
        log_action(
            request_obj,
            actor=actor,
            action='assigned',
            message=f'Mở bước {step.step_order} → {step.assignee.username}',
            step=step,
        )
    elif step.target_department:
        log_action(
            request_obj,
            actor=actor,
            action='queued',
            message=f'Mở bước {step.step_order} → phòng {step.target_department.name}',
            step=step,
        )


@transaction.atomic
def create_request_with_steps(
    *,
    requester,
    request_type,
    title,
    description,
    line_items=None,
    recurring_item=None,
    needs_advance=False,
    advance_amount=None,
):
    is_from_catalog = bool(recurring_item)
    service_request = ServiceRequest.objects.create(
        requester=requester,
        request_type=request_type,
        title=title,
        description=description,
        recurring_item=recurring_item,
        is_from_catalog=is_from_catalog,
        needs_advance=needs_advance,
        advance_amount=advance_amount if needs_advance else None,
    )

    if line_items:
        for idx, item in enumerate(line_items):
            ProcurementLineItem.objects.create(
                request=service_request,
                recurring_item=item.get('recurring_item'),
                description=item['description'],
                quantity_requested=item.get('quantity', Decimal('1')),
                unit=item.get('unit', 'cái'),
                sort_order=idx,
            )
    elif recurring_item:
        ProcurementLineItem.objects.create(
            request=service_request,
            recurring_item=recurring_item,
            description=recurring_item.name,
            quantity_requested=Decimal('1'),
            unit=recurring_item.unit,
            sort_order=0,
        )

    if not service_request.line_items.exists():
        raise ValueError('Vui lòng thêm ít nhất một dòng hàng.')

    steps = _build_initial_steps(service_request, requester)
    if not steps:
        raise ValueError('Không thể tạo quy trình xử lý.')

    log_action(service_request, actor=requester, action='created', message='Gửi yêu cầu mua hàng')
    first_active = service_request.steps.exclude(
        status=ServiceRequestStep.STATUS_SKIPPED,
    ).order_by('step_order').first()
    if first_active:
        _log_step_opened(service_request, requester, first_active)

    return service_request


def unlock_next_steps(completed_step):
    unlocked = []
    requester = completed_step.request.requester
    for child in ServiceRequestStep.objects.filter(
        request_id=completed_step.request_id,
        depends_on_id=completed_step.pk,
        status=ServiceRequestStep.STATUS_BLOCKED,
    ):
        child.status = ServiceRequestStep.STATUS_PENDING
        if child.assignee_rule == RequestTypeStepTemplate.RULE_DIRECT_MANAGER:
            if child.step_code == ServiceRequestStep.STEP_RECEIPT:
                receiver = completed_step.request.goods_receiver
                child.assignee = receiver
            else:
                child.assignee = _resolve_assignee(child.assignee_rule, requester)
        elif child.assignee_rule == RequestTypeStepTemplate.RULE_DIRECTOR:
            child.assignee = find_director_user()
        child.save(update_fields=['status', 'assignee'])
        unlocked.append(child)
    return unlocked


def _maybe_complete_request(request_obj, *, actor):
    if not _remaining_steps(request_obj).exists():
        request_obj.status = ServiceRequest.STATUS_COMPLETED
        request_obj.completed_at = timezone.now()
        request_obj.save(update_fields=['status', 'completed_at', 'updated_at'])
        log_action(request_obj, actor=actor, action='completed', message='Yêu cầu hoàn thành')
        return True
    return False


def _complete_step(step, *, actor, note=''):
    step.status = ServiceRequestStep.STATUS_COMPLETED
    step.note = note or step.note
    step.completed_at = timezone.now()
    step.save(update_fields=['status', 'note', 'completed_at'])

    log_action(
        step.request,
        actor=actor,
        action='step_completed',
        message=note or f'Hoàn thành: {step.name}',
        step=step,
    )
    return unlock_next_steps(step)


@transaction.atomic
def approve_step(step, *, actor, note=''):
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể duyệt.')

    unlocked = _complete_step(step, actor=actor, note=note)
    request_obj = step.request

    if not _maybe_complete_request(request_obj, actor=actor):
        for child in unlocked:
            _log_step_opened(request_obj, actor, child)

    return request_obj


@transaction.atomic
def reject_step(step, *, actor, reason):
    if not reason.strip():
        raise ValueError('Vui lòng nhập lý do từ chối.')

    step.status = ServiceRequestStep.STATUS_REJECTED
    step.note = reason.strip()
    step.completed_at = timezone.now()
    step.save(update_fields=['status', 'note', 'completed_at'])

    request_obj = step.request
    request_obj.status = ServiceRequest.STATUS_REJECTED
    request_obj.save(update_fields=['status', 'updated_at'])

    log_action(
        request_obj,
        actor=actor,
        action='rejected',
        message=reason.strip(),
        step=step,
    )
    return request_obj


@transaction.atomic
def claim_step(step, *, actor):
    if step.assignee_rule not in {
        RequestTypeStepTemplate.RULE_DEPARTMENT_QUEUE,
        RequestTypeStepTemplate.RULE_DIRECTOR,
    }:
        raise ValueError('Bước này không cần tiếp nhận.')
    if step.assignee_id:
        raise ValueError('Bước đã có người tiếp nhận.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể tiếp nhận.')

    step.assignee = actor
    if step.is_execution:
        step.status = ServiceRequestStep.STATUS_IN_PROGRESS
    step.save(update_fields=['assignee', 'status'])

    log_action(
        step.request,
        actor=actor,
        action='claimed',
        message=f'{actor.username} tiếp nhận bước {step.step_order}',
        step=step,
    )
    return step


@transaction.atomic
def complete_procurement_quote(step, *, actor, line_updates, note=''):
    """Thu mua xác nhận SL, nhập báo giá NCC và chọn NCC."""
    if step.step_code != ServiceRequestStep.STEP_PROCUREMENT_QUOTE:
        raise ValueError('Bước không phải kiểm tra giá.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể hoàn thành.')

    request_obj = step.request
    for line in request_obj.line_items.all():
        data = line_updates.get(line.pk)
        if not data:
            raise ValueError(f'Thiếu dữ liệu dòng "{line.description}".')

        qty = data.get('quantity_confirmed')
        if qty is None or qty <= 0:
            raise ValueError(f'Dòng "{line.description}": vui lòng nhập số lượng hợp lệ.')
        line.quantity_confirmed = qty
        line.save(update_fields=['quantity_confirmed'])

        quotes_data = data.get('quotes', [])
        if not quotes_data:
            raise ValueError(f'Dòng "{line.description}": cần ít nhất một báo giá NCC.')

        selected_ids = []
        line.quotes.all().delete()
        for quote_data in quotes_data:
            supplier = (quote_data.get('supplier_name') or '').strip()
            unit_price = quote_data.get('unit_price')
            if not supplier or unit_price is None:
                continue
            quote = ProcurementSupplierQuote.objects.create(
                line_item=line,
                supplier_name=supplier,
                unit_price=unit_price,
                quote_file=quote_data.get('quote_file'),
                is_selected=bool(quote_data.get('is_selected')),
            )
            if quote.is_selected:
                selected_ids.append(quote.pk)

        if len(selected_ids) != 1:
            raise ValueError(f'Dòng "{line.description}": chọn đúng một nhà cung cấp.')

    _complete_step(step, actor=actor, note=note)
    return _insert_post_quote_steps(request_obj, after_step=step, actor=actor)


@transaction.atomic
def complete_purchase_step(step, *, actor, goods_receiver, note=''):
    if step.step_code != ServiceRequestStep.STEP_PURCHASE:
        raise ValueError('Bước không phải đặt hàng.')
    if not goods_receiver:
        raise ValueError('Vui lòng chọn người nhận hàng.')

    request_obj = step.request
    request_obj.goods_receiver = goods_receiver
    request_obj.save(update_fields=['goods_receiver', 'updated_at'])

    unlocked = _complete_step(step, actor=actor, note=note)
    for child in unlocked:
        if child.step_code == ServiceRequestStep.STEP_RECEIPT:
            child.assignee = goods_receiver
            child.save(update_fields=['assignee'])
        _log_step_opened(request_obj, actor, child)

    _maybe_complete_request(request_obj, actor=actor)
    return request_obj


@transaction.atomic
def complete_execution_step(step, *, actor, note):
    if not step.is_execution:
        raise ValueError('Bước này không phải bước thực hiện.')
    if step.status not in ServiceRequestStep.OPEN_HANDLER_STATUSES:
        raise ValueError('Bước không thể hoàn thành.')

    unlocked = _complete_step(step, actor=actor, note=note)
    request_obj = step.request
    if not _maybe_complete_request(request_obj, actor=actor):
        for child in unlocked:
            _log_step_opened(request_obj, actor, child)
    return request_obj


@transaction.atomic
def cancel_request(request_obj, *, actor):
    if request_obj.requester_id != actor.id:
        raise ValueError('Chỉ người gửi mới hủy được.')
    if request_obj.status != ServiceRequest.STATUS_IN_PROGRESS:
        raise ValueError('Yêu cầu không thể hủy.')

    first_step = request_obj.steps.exclude(
        status=ServiceRequestStep.STATUS_SKIPPED,
    ).order_by('step_order').first()
    if first_step and first_step.status != ServiceRequestStep.STATUS_PENDING:
        raise ValueError('Không thể hủy — yêu cầu đã được xử lý.')

    request_obj.status = ServiceRequest.STATUS_CANCELLED
    request_obj.save(update_fields=['status', 'updated_at'])
    log_action(request_obj, actor=actor, action='cancelled', message='Người gửi hủy yêu cầu')
    return request_obj


def get_active_request_type():
    return RequestType.objects.filter(
        is_active=True,
        code=RequestType.CODE_ASSET_PURCHASE,
    ).first()
