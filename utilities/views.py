from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Count, Q, Sum, Value
from django.db.models.functions import Coalesce, NullIf
from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from assessment.decorators import module_perm_required
from hrm.menu_permissions import (
    user_can_access_menu,
    user_can_create_menu,
    user_can_export_menu,
    user_can_update_menu,
)
from hrm.module_permissions import MODULE_UTILITIES
from PortalJustPlay.list_search import apply_user_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset

from utilities.excel_export import (
    export_meal_stats_xlsx,
    export_meal_summary_xlsx,
    export_salary_advances_xlsx,
    export_salary_stats_xlsx,
)
from utilities.forms import (
    MealDayMenuForm,
    MealDishForm,
    MealOrderForm,
    MealOrderSettingsForm,
    SalaryAdvanceForm,
)
from utilities.meal_rules import (
    current_orderable_meal_date,
    format_order_window,
    is_meal_order_window_open,
    meal_order_window_for,
    next_orderable_meal_date,
)
from utilities.models import (
    MealDayOffering,
    MealDish,
    MealOrder,
    MealOrderDecline,
    MealOrderSettings,
    SalaryAdvanceRequest,
    ScheduleReminder,
)
from utilities.salary_rules import (
    current_advance_month,
    is_salary_advance_open,
    salary_advance_window_label,
)
from utilities.date_range_filter import (
    date_range_from_span,
    date_range_span_context,
    parse_date_range_span_from_request,
)


def _can_manage_meals(user) -> bool:
    return user_can_update_menu(user, MODULE_UTILITIES, 'meal_ordering')


def _parse_meal_date(raw: str | None, *, default):
    if not raw:
        return default
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return default


def _meal_summary_filters(request):
    """Từ–đến ngày (preset span) + lọc món cho tổng hợp đặt cơm."""
    default_to = current_orderable_meal_date() or next_orderable_meal_date() or timezone.localdate()
    span = parse_date_range_span_from_request(request)

    # Tương thích URL cũ ?meal_date=...
    legacy = _parse_meal_date(request.GET.get('meal_date'), default=None)
    date_from = _parse_meal_date(
        request.GET.get('date_from') or request.GET.get('from'),
        default=None,
    )
    date_to = _parse_meal_date(
        request.GET.get('date_to') or request.GET.get('to'),
        default=None,
    )
    if legacy and not date_from and not date_to:
        date_from = date_to = legacy
    if not date_to:
        date_to = default_to
    if not date_from:
        date_from = date_range_from_span(date_to, span)
    if date_from > date_to:
        date_from, date_to = date_to, date_from

    dish_raw = (request.GET.get('dish') or '').strip()
    dish_id = int(dish_raw) if dish_raw.isdigit() else None
    selected_dish = MealDish.objects.filter(pk=dish_id).first() if dish_id else None

    return {
        'date_from': date_from,
        'date_to': date_to,
        'dish_id': selected_dish.pk if selected_dish else None,
        'selected_dish': selected_dish,
        **date_range_span_context(date_from, date_to),
    }


def _meal_summary_query_string(filters: dict) -> str:
    parts = [
        f'date_from={filters["date_from"].isoformat()}',
        f'date_to={filters["date_to"].isoformat()}',
    ]
    if filters.get('range_span'):
        parts.append(f'span={filters["range_span"]}')
    if filters.get('dish_id'):
        parts.append(f'dish={filters["dish_id"]}')
    return '&'.join(parts)


def _can_manage_salary(user) -> bool:
    return user_can_update_menu(user, MODULE_UTILITIES, 'salary_advance')


def _offered_dish_ids(meal_date):
    return list(
        MealDayOffering.objects.filter(meal_date=meal_date, is_offered=True)
        .values_list('dish_id', flat=True)
    )


def _meal_menu_lock_reason(meal_date) -> str | None:
    """Trả về lý do khóa sửa menu ngày, hoặc None nếu còn sửa được."""
    today = timezone.localdate()
    if meal_date < today:
        return 'Menu ngày đã qua đã khóa — chỉ xem, không sửa.'
    if MealOrder.objects.filter(meal_date=meal_date).exists():
        return 'Đã có đơn đặt cho ngày này — menu đã khóa để không lệch lịch sử.'
    return None


def _ensure_day_offerings(meal_date):
    dishes = MealDish.objects.filter(is_active=True)
    existing = {
        row.dish_id: row
        for row in MealDayOffering.objects.filter(meal_date=meal_date, dish__in=dishes)
    }
    for dish in dishes:
        if dish.pk not in existing:
            MealDayOffering.objects.create(meal_date=meal_date, dish=dish, is_offered=False)


def _meal_stats_rows(*, date_from, date_to):
    qs = (
        MealOrder.objects.filter(meal_date__gte=date_from, meal_date__lte=date_to)
        .annotate(label=Coalesce(NullIf('dish_name', Value('')), 'dish__name'))
        .values('meal_date', 'label')
        .annotate(count=Count('id'))
        .order_by('meal_date', '-count', 'label')
    )
    rows = [
        {
            'day': row['meal_date'].strftime('%d/%m/%Y'),
            'meal_date': row['meal_date'],
            'dish': row['label'],
            'count': row['count'],
        }
        for row in qs
    ]
    if date_from == date_to:
        period_label = date_from.isoformat()
    else:
        period_label = f'{date_from.isoformat()}_{date_to.isoformat()}'
    return rows, period_label


def _meal_stats_totals(rows):
    """Gộp số lượng theo tên món trên cả khoảng."""
    totals = {}
    for row in rows:
        totals[row['dish']] = totals.get(row['dish'], 0) + row['count']
    return sorted(
        [{'dish': name, 'count': count} for name, count in totals.items()],
        key=lambda r: (-r['count'], r['dish']),
    )


@module_perm_required(MODULE_UTILITIES, 'view')
def utilities_hub(request):
    if user_can_access_menu(request.user, MODULE_UTILITIES, 'meal_ordering'):
        return redirect('utilities:meal_home')
    if user_can_access_menu(request.user, MODULE_UTILITIES, 'salary_advance'):
        return redirect('utilities:salary_home')
    messages.error(request, 'Bạn chưa được cấp quyền Tiện ích.')
    return redirect('home_portal')


# --- Đặt cơm ---


@module_perm_required(MODULE_UTILITIES, 'view')
def meal_home(request):
    meal_date = current_orderable_meal_date()
    if meal_date is None:
        meal_date = next_orderable_meal_date()
    window_open = bool(meal_date and is_meal_order_window_open(meal_date))
    offered_ids = _offered_dish_ids(meal_date) if meal_date else []
    existing = None
    if meal_date and request.user.is_authenticated:
        existing = MealOrder.objects.filter(employee=request.user, meal_date=meal_date).select_related('dish').first()

    can_order = (
        window_open
        and user_can_create_menu(request.user, MODULE_UTILITIES, 'meal_ordering')
        and offered_ids
    )
    form = None
    if can_order and request.method == 'POST':
        form = MealOrderForm(
            request.POST,
            meal_date=meal_date,
            offered_dish_ids=offered_ids,
        )
        if form.is_valid():
            order = form.save(commit=False)
            order.employee = request.user
            order.meal_date = meal_date
            order.dish_name = order.dish.name
            order.save()
            messages.success(request, f'Đã đặt {order.dish.name} cho ngày {meal_date.strftime("%d/%m/%Y")}.')
            return redirect('utilities:meal_home')
    elif can_order:
        form = MealOrderForm(meal_date=meal_date, offered_dish_ids=offered_ids)

    window_start, window_end = meal_order_window_for(meal_date) if meal_date else (None, None)
    return render(request, 'utilities/meal_home.html', {
        'meal_date': meal_date,
        'window_open': window_open,
        'window_label': format_order_window(meal_date) if meal_date else '',
        'window_start': window_start,
        'window_end': window_end,
        'offered_count': len(offered_ids),
        'existing_order': existing,
        'form': form,
        'can_order': can_order,
        'can_manage': _can_manage_meals(request.user),
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_dish_list(request):
    dishes = list(MealDish.objects.all())
    ordered_ids = set(
        MealOrder.objects.filter(dish_id__in=[d.pk for d in dishes])
        .values_list('dish_id', flat=True)
        .distinct()
    )
    for dish in dishes:
        dish.has_orders = dish.pk in ordered_ids
    return render(request, 'utilities/meal_dish_list.html', {
        'dishes': dishes,
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_dish_create(request):
    if request.method == 'POST':
        form = MealDishForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã thêm món.')
            return redirect('utilities:meal_dish_list')
    else:
        next_order = MealDish.objects.count() + 1
        form = MealDishForm(initial={'sort_order': next_order, 'is_active': True})
    return render(request, 'utilities/meal_dish_form.html', {
        'form': form,
        'title': 'Thêm món',
        'has_orders': False,
        'lock_name': False,
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_dish_edit(request, pk):
    dish = get_object_or_404(MealDish, pk=pk)
    has_orders = MealOrder.objects.filter(dish=dish).exists()
    lock_name = has_orders
    if request.method == 'POST':
        form = MealDishForm(request.POST, instance=dish, lock_name=lock_name)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật món.')
            return redirect('utilities:meal_dish_list')
    else:
        form = MealDishForm(instance=dish, lock_name=lock_name)
    return render(request, 'utilities/meal_dish_form.html', {
        'form': form,
        'title': 'Sửa món',
        'dish': dish,
        'has_orders': has_orders,
        'lock_name': lock_name,
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_dish_delete(request, pk):
    dish = get_object_or_404(MealDish, pk=pk)
    if request.method == 'POST':
        if MealOrder.objects.filter(dish=dish).exists():
            messages.error(request, 'Không xóa được — món đã có đơn đặt.')
        elif MealDayOffering.objects.filter(dish=dish, is_offered=True).exists():
            messages.error(request, 'Không xóa được — món đang/đã nằm trong menu ngày.')
        else:
            dish.delete()
            messages.success(request, 'Đã xóa món.')
        return redirect('utilities:meal_dish_list')
    return render(request, 'utilities/meal_dish_confirm_delete.html', {'dish': dish})


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_day_menu(request):
    default_date = next_orderable_meal_date()
    meal_date = _parse_meal_date(
        request.GET.get('meal_date') or request.POST.get('meal_date'),
        default=default_date,
    )

    _ensure_day_offerings(meal_date)
    offerings = MealDayOffering.objects.filter(meal_date=meal_date).select_related('dish')
    lock_reason = _meal_menu_lock_reason(meal_date)
    menu_locked = lock_reason is not None

    if request.method == 'POST':
        if menu_locked:
            messages.error(request, lock_reason)
            return redirect(f'{reverse("utilities:meal_day_menu")}?meal_date={meal_date.isoformat()}')
        selected = {int(pk) for pk in request.POST.getlist('offered') if pk.isdigit()}
        for row in offerings:
            row.is_offered = row.dish_id in selected
            if row.is_offered:
                row.dish_name = row.dish.name
            row.save(update_fields=['is_offered', 'dish_name'])
        messages.success(request, f'Đã cập nhật menu ngày {meal_date.strftime("%d/%m/%Y")}.')
        return redirect(f'{reverse("utilities:meal_day_menu")}?meal_date={meal_date.isoformat()}')

    return render(request, 'utilities/meal_day_menu.html', {
        'meal_date': meal_date,
        'offerings': offerings,
        'menu_locked': menu_locked,
        'lock_reason': lock_reason,
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_summary(request):
    filters = _meal_summary_filters(request)
    date_from = filters['date_from']
    date_to = filters['date_to']
    dish_id = filters['dish_id']

    orders_qs = MealOrder.objects.filter(
        meal_date__gte=date_from,
        meal_date__lte=date_to,
    )
    if dish_id:
        orders_qs = orders_qs.filter(dish_id=dish_id)

    orders = (
        orders_qs
        .select_related('employee__profile', 'employee__profile__department', 'dish')
        .annotate(
            employee_name=Coalesce('employee__profile__full_name', 'employee__username'),
            department_name=Coalesce('employee__profile__department__name', Value('')),
        )
        .order_by('meal_date', 'employee_name')
    )
    declines = (
        MealOrderDecline.objects.filter(
            meal_date__gte=date_from,
            meal_date__lte=date_to,
        )
        .select_related('employee__profile', 'employee__profile__department')
        .annotate(
            employee_name=Coalesce('employee__profile__full_name', 'employee__username'),
            department_name=Coalesce('employee__profile__department__name', Value('')),
        )
        .order_by('meal_date', 'employee_name')
    )
    show_meal_date_col = date_from != date_to

    # Menu từng ngày (MealDayOffering) — dùng snapshot tên món, không lấy tên danh mục hiện tại.
    offered_rows = list(
        MealDayOffering.objects.filter(
            meal_date__gte=date_from,
            meal_date__lte=date_to,
            is_offered=True,
        )
        .select_related('dish')
        .order_by('meal_date', 'dish__sort_order', 'dish__name')
    )
    menus_by_day = []
    current_menu = None
    for row in offered_rows:
        if current_menu is None or current_menu['date'] != row.meal_date:
            current_menu = {'date': row.meal_date, 'dishes': []}
            menus_by_day.append(current_menu)
        current_menu['dishes'].append({
            'id': row.dish_id,
            'name': row.dish_name or row.dish.name,
        })

    order_counts = {
        (row['meal_date'], row['label']): row['count']
        for row in (
            orders_qs
            .annotate(label=Coalesce(NullIf('dish_name', Value('')), 'dish__name'))
            .values('meal_date', 'label')
            .annotate(count=Count('id'))
        )
    }
    totals_by_day = []
    for day in menus_by_day:
        if dish_id:
            rows = [
                {'dish__name': name, 'count': count}
                for (d, name), count in order_counts.items()
                if d == day['date']
            ]
            for dish in day['dishes']:
                if dish['id'] == dish_id and not any(r['dish__name'] == dish['name'] for r in rows):
                    rows.append({'dish__name': dish['name'], 'count': 0})
            rows.sort(key=lambda r: (-r['count'], r['dish__name']))
        else:
            rows = [
                {
                    'dish__name': dish['name'],
                    'count': order_counts.get((day['date'], dish['name']), 0),
                }
                for dish in day['dishes']
            ]
            offered_names = {dish['name'] for dish in day['dishes']}
            extras = [
                {'dish__name': name, 'count': count}
                for (d, name), count in order_counts.items()
                if d == day['date'] and name not in offered_names
            ]
            extras.sort(key=lambda r: (-r['count'], r['dish__name']))
            rows.extend(extras)
        if rows:
            totals_by_day.append({'date': day['date'], 'rows': rows})    # Ngày có đơn nhưng chưa cấu hình menu
    menu_dates = {day['date'] for day in menus_by_day}
    orphan_dates = sorted({d for (d, _name) in order_counts if d not in menu_dates})
    for d in orphan_dates:
        rows = [
            {'dish__name': name, 'count': count}
            for (od, name), count in order_counts.items()
            if od == d
        ]
        rows.sort(key=lambda r: (-r['count'], r['dish__name']))
        if rows:
            totals_by_day.append({'date': d, 'rows': rows})
    totals_by_day.sort(key=lambda day: day['date'])

    offered_dish_ids = {row.dish_id for row in offered_rows}
    dishes = MealDish.objects.filter(pk__in=offered_dish_ids).order_by('sort_order', 'name')
    if dish_id and not dishes.filter(pk=dish_id).exists():
        dishes = MealDish.objects.filter(Q(pk__in=offered_dish_ids) | Q(pk=dish_id)).order_by('sort_order', 'name')

    return render(request, 'utilities/meal_summary.html', {
        **filters,
        'meal_date': date_to,
        'orders': orders,
        'declines': declines,
        'menus_by_day': menus_by_day,
        'totals_by_day': totals_by_day,
        'dishes': dishes,
        'filter_query': _meal_summary_query_string(filters),
        'show_meal_date_col': show_meal_date_col,
        'can_export': user_can_export_menu(request.user, MODULE_UTILITIES, 'meal_ordering'),
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'export')
def meal_summary_export(request):
    if not _can_manage_meals(request.user):
        raise Http404
    filters = _meal_summary_filters(request)
    return export_meal_summary_xlsx(
        date_from=filters['date_from'],
        date_to=filters['date_to'],
        dish_id=filters['dish_id'],
    )


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_stats(request):
    filters = _meal_summary_filters(request)
    date_from = filters['date_from']
    date_to = filters['date_to']
    stats_rows, period_label = _meal_stats_rows(date_from=date_from, date_to=date_to)
    stats_by_day = []
    current = None
    for row in stats_rows:
        if current is None or current['date'] != row['meal_date']:
            current = {'date': row['meal_date'], 'rows': []}
            stats_by_day.append(current)
        current['rows'].append(row)
    return render(request, 'utilities/meal_stats.html', {
        **filters,
        'stats_rows': stats_rows,
        'stats_by_day': stats_by_day,
        'stats_totals': _meal_stats_totals(stats_rows),
        'period_label': period_label,
        'filter_query': _meal_summary_query_string({**filters, 'dish_id': None}),
        'show_meal_date_col': date_from != date_to,
        'can_export': user_can_export_menu(request.user, MODULE_UTILITIES, 'meal_ordering'),
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'export')
def meal_stats_export(request):
    if not _can_manage_meals(request.user):
        raise Http404
    filters = _meal_summary_filters(request)
    rows, label = _meal_stats_rows(
        date_from=filters['date_from'],
        date_to=filters['date_to'],
    )
    return export_meal_stats_xlsx(rows, period_label=label)


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_settings(request):
    settings = MealOrderSettings.load()
    if request.method == 'POST':
        form = MealOrderSettingsForm(request.POST, instance=settings)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật khung giờ đặt cơm.')
            return redirect('utilities:meal_settings')
    else:
        form = MealOrderSettingsForm(instance=settings)
    return render(request, 'utilities/meal_settings.html', {
        'form': form,
        'settings': settings,
        'window_example': format_order_window(next_orderable_meal_date()),
        'can_manage': True,
    })


# --- Ứng lương ---


@module_perm_required(MODULE_UTILITIES, 'view')
def salary_home(request):
    month = current_advance_month()
    existing = SalaryAdvanceRequest.objects.filter(
        employee=request.user, request_month=month,
    ).first()
    window_open = is_salary_advance_open()
    can_request = window_open and user_can_create_menu(request.user, MODULE_UTILITIES, 'salary_advance')

    if can_request and not existing and request.method == 'POST':
        form = SalaryAdvanceForm(
            request.POST,
            employee=request.user,
            request_month=month,
        )
        if form.is_valid():
            req = form.save(commit=False)
            req.employee = request.user
            req.request_month = month
            try:
                req.save()
            except IntegrityError:
                messages.error(
                    request,
                    'Bạn đã ứng lương tháng này rồi. Mỗi tài khoản chỉ được ứng 1 lần/tháng.',
                )
                return redirect('utilities:salary_home')
            messages.success(request, 'Đã gửi yêu cầu ứng lương.')
            return redirect('utilities:salary_home')
    else:
        form = (
            SalaryAdvanceForm(employee=request.user, request_month=month)
            if can_request and not existing
            else None
        )

    history = SalaryAdvanceRequest.objects.filter(employee=request.user).order_by('-request_month')[:12]
    return render(request, 'utilities/salary_home.html', {
        'window_open': window_open,
        'window_label': salary_advance_window_label(),
        'request_month': month,
        'existing_request': existing,
        'form': form,
        'can_request': can_request,
        'history': history,
        'can_manage': _can_manage_salary(request.user),
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def salary_manage(request):
    search_query = get_search_query(request)
    month_raw = request.GET.get('month')
    qs = SalaryAdvanceRequest.objects.select_related('employee__profile', 'employee__profile__department')
    if month_raw:
        month = datetime.strptime(month_raw, '%Y-%m').date().replace(day=1)
        qs = qs.filter(request_month=month)
    else:
        month = current_advance_month()
        qs = qs.filter(request_month=month)
    qs = qs.order_by('-created_at')
    qs = apply_user_search(qs, search_query, prefix='employee__')
    page_obj, query_string = paginate_queryset(request, qs)
    aggregate = qs.aggregate(total=Sum('amount'), count=Count('id'))
    return render(request, 'utilities/salary_manage.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'selected_month': month,
        'total_amount': aggregate['total'] or Decimal('0'),
        'total_count': aggregate['count'] or 0,
        'can_export': user_can_export_menu(request.user, MODULE_UTILITIES, 'salary_advance'),
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'export')
def salary_manage_export(request):
    if not _can_manage_salary(request.user):
        raise Http404
    month_raw = request.GET.get('month')
    qs = SalaryAdvanceRequest.objects.all()
    if month_raw:
        month = datetime.strptime(month_raw, '%Y-%m').date().replace(day=1)
        qs = qs.filter(request_month=month)
    return export_salary_advances_xlsx(qs)


@module_perm_required(MODULE_UTILITIES, 'update')
def salary_stats(request):
    rows = []
    qs = (
        SalaryAdvanceRequest.objects.values('request_month')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-request_month')[:24]
    )
    for row in qs:
        rows.append({
            'month': row['request_month'].strftime('%m/%Y'),
            'count': row['count'],
            'total': int(row['total'] or 0),
        })
    return render(request, 'utilities/salary_stats.html', {
        'stats_rows': rows,
        'can_export': user_can_export_menu(request.user, MODULE_UTILITIES, 'salary_advance'),
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'export')
def salary_stats_export(request):
    if not _can_manage_salary(request.user):
        raise Http404
    rows = []
    qs = (
        SalaryAdvanceRequest.objects.values('request_month')
        .annotate(count=Count('id'), total=Sum('amount'))
        .order_by('-request_month')[:24]
    )
    for row in qs:
        rows.append({
            'month': row['request_month'].strftime('%m/%Y'),
            'count': row['count'],
            'total': int(row['total'] or 0),
        })
    return export_salary_stats_xlsx(rows)


# --- Nhắc lịch ---


@login_required
def schedule_reminder_home(request):
    return redirect('tools:schedule_reminder')


@login_required
@require_POST
def schedule_reminder_delete(request, pk):
    reminder = get_object_or_404(ScheduleReminder, pk=pk, user=request.user)
    reminder.is_active = False
    reminder.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, 'Đã xóa nhắc lịch.')
    return redirect('tools:schedule_reminder')
