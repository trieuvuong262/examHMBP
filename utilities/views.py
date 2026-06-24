from datetime import datetime, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Sum, Value
from django.db.models.functions import Coalesce
from django.http import Http404
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
    MealStatsFilterForm,
    SalaryAdvanceForm,
    ScheduleReminderForm,
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


def _can_manage_meals(user) -> bool:
    return user_can_update_menu(user, MODULE_UTILITIES, 'meal_ordering')


def _parse_meal_date(raw: str | None, *, default):
    if not raw:
        return default
    try:
        return datetime.strptime(raw, '%Y-%m-%d').date()
    except ValueError:
        return default


def _can_manage_salary(user) -> bool:
    return user_can_update_menu(user, MODULE_UTILITIES, 'salary_advance')


def _can_schedule_reminder(user) -> bool:
    return user_can_access_menu(user, MODULE_UTILITIES, 'schedule_reminder')


def _can_manage_schedule_reminder(user) -> bool:
    return user_can_create_menu(user, MODULE_UTILITIES, 'schedule_reminder')


def _offered_dish_ids(meal_date):
    return list(
        MealDayOffering.objects.filter(meal_date=meal_date, is_offered=True)
        .values_list('dish_id', flat=True)
    )


def _ensure_day_offerings(meal_date):
    dishes = MealDish.objects.filter(is_active=True)
    existing = {
        row.dish_id: row
        for row in MealDayOffering.objects.filter(meal_date=meal_date, dish__in=dishes)
    }
    for dish in dishes:
        if dish.pk not in existing:
            MealDayOffering.objects.create(meal_date=meal_date, dish=dish, is_offered=False)


def _meal_stats_rows(period: str, anchor_date):
    if period == MealStatsFilterForm.PERIOD_MONTH:
        start = anchor_date.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1, day=1)
        else:
            end = start.replace(month=start.month + 1, day=1)
        label = start.strftime('%m/%Y')
    else:
        start = anchor_date - timedelta(days=anchor_date.weekday())
        end = start + timedelta(days=7)
        label = f'tuan_{start.isoformat()}'
    qs = (
        MealOrder.objects.filter(meal_date__gte=start, meal_date__lt=end)
        .values('meal_date', 'dish__name')
        .annotate(count=Count('id'))
        .order_by('meal_date', '-count')
    )
    rows = [
        {
            'day': row['meal_date'].strftime('%d/%m/%Y'),
            'dish': row['dish__name'],
            'count': row['count'],
        }
        for row in qs
    ]
    return rows, label


@module_perm_required(MODULE_UTILITIES, 'view')
def utilities_hub(request):
    if user_can_access_menu(request.user, MODULE_UTILITIES, 'meal_ordering'):
        return redirect('utilities:meal_home')
    if user_can_access_menu(request.user, MODULE_UTILITIES, 'salary_advance'):
        return redirect('utilities:salary_home')
    if user_can_access_menu(request.user, MODULE_UTILITIES, 'schedule_reminder'):
        return redirect('utilities:schedule_reminder_home')
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
    dishes = MealDish.objects.all()
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
    return render(request, 'utilities/meal_dish_form.html', {'form': form, 'title': 'Thêm món'})


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_dish_edit(request, pk):
    dish = get_object_or_404(MealDish, pk=pk)
    if request.method == 'POST':
        form = MealDishForm(request.POST, instance=dish)
        if form.is_valid():
            form.save()
            messages.success(request, 'Đã cập nhật món.')
            return redirect('utilities:meal_dish_list')
    else:
        form = MealDishForm(instance=dish)
    return render(request, 'utilities/meal_dish_form.html', {'form': form, 'title': 'Sửa món', 'dish': dish})


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_dish_delete(request, pk):
    dish = get_object_or_404(MealDish, pk=pk)
    if request.method == 'POST':
        if MealOrder.objects.filter(dish=dish).exists():
            messages.error(request, 'Không xóa được — món đã có đơn đặt.')
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

    if request.method == 'POST':
        selected = {int(pk) for pk in request.POST.getlist('offered') if pk.isdigit()}
        for row in offerings:
            row.is_offered = row.dish_id in selected
            row.save(update_fields=['is_offered'])
        messages.success(request, f'Đã cập nhật menu ngày {meal_date.strftime("%d/%m/%Y")}.')
        return redirect(f'{reverse("utilities:meal_day_menu")}?meal_date={meal_date.isoformat()}')

    return render(request, 'utilities/meal_day_menu.html', {
        'meal_date': meal_date,
        'offerings': offerings,
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_summary(request):
    default_date = current_orderable_meal_date() or next_orderable_meal_date()
    meal_date = _parse_meal_date(request.GET.get('meal_date'), default=default_date)
    orders = (
        MealOrder.objects.filter(meal_date=meal_date)
        .select_related('employee__profile', 'employee__profile__department', 'dish')
        .annotate(
            employee_name=Coalesce('employee__profile__full_name', 'employee__username'),
            department_name=Coalesce('employee__profile__department__name', Value('')),
        )
        .order_by('employee_name')
    )
    declines = (
        MealOrderDecline.objects.filter(meal_date=meal_date)
        .select_related('employee__profile', 'employee__profile__department')
        .annotate(
            employee_name=Coalesce('employee__profile__full_name', 'employee__username'),
            department_name=Coalesce('employee__profile__department__name', Value('')),
        )
        .order_by('employee_name')
    )
    totals = (
        MealOrder.objects.filter(meal_date=meal_date)
        .values('dish__name')
        .annotate(count=Count('id'))
        .order_by('-count', 'dish__name')
    )
    return render(request, 'utilities/meal_summary.html', {
        'meal_date': meal_date,
        'orders': orders,
        'declines': declines,
        'totals': totals,
        'can_export': user_can_export_menu(request.user, MODULE_UTILITIES, 'meal_ordering'),
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'export')
def meal_summary_export(request):
    if not _can_manage_meals(request.user):
        raise Http404
    meal_date = _parse_meal_date(request.GET.get('meal_date'), default=None)
    if not meal_date:
        raise Http404
    return export_meal_summary_xlsx(meal_date)


@module_perm_required(MODULE_UTILITIES, 'update')
def meal_stats(request):
    today = timezone.localdate()
    if request.method == 'GET' and request.GET.get('period'):
        filter_form = MealStatsFilterForm(request.GET)
    else:
        filter_form = MealStatsFilterForm(initial={
            'period': MealStatsFilterForm.PERIOD_WEEK,
            'anchor_date': today,
        })
    stats_rows = []
    period_label = ''
    if filter_form.is_valid():
        stats_rows, period_label = _meal_stats_rows(
            filter_form.cleaned_data['period'],
            filter_form.cleaned_data['anchor_date'],
        )
    return render(request, 'utilities/meal_stats.html', {
        'filter_form': filter_form,
        'stats_rows': stats_rows,
        'period_label': period_label,
        'can_export': user_can_export_menu(request.user, MODULE_UTILITIES, 'meal_ordering'),
        'can_manage': True,
    })


@module_perm_required(MODULE_UTILITIES, 'export')
def meal_stats_export(request):
    if not _can_manage_meals(request.user):
        raise Http404
    filter_form = MealStatsFilterForm(request.GET)
    if not filter_form.is_valid():
        raise Http404
    rows, label = _meal_stats_rows(
        filter_form.cleaned_data['period'],
        filter_form.cleaned_data['anchor_date'],
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
        form = SalaryAdvanceForm(request.POST)
        if form.is_valid():
            req = form.save(commit=False)
            req.employee = request.user
            req.request_month = month
            req.save()
            messages.success(request, 'Đã gửi yêu cầu ứng lương.')
            return redirect('utilities:salary_home')
    else:
        form = SalaryAdvanceForm() if can_request and not existing else None

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


@module_perm_required(MODULE_UTILITIES, 'view')
def schedule_reminder_home(request):
    if not _can_schedule_reminder(request.user):
        messages.error(request, 'Bạn chưa được cấp quyền Nhắc lịch.')
        return redirect('home_portal')

    can_manage = _can_manage_schedule_reminder(request.user)
    now = timezone.now()
    reminders = list(
        ScheduleReminder.objects.filter(user=request.user, is_active=True)
        .order_by('remind_at', '-created_at')[:50],
    )
    upcoming = [r for r in reminders if r.push_sent_at is None and r.remind_at > now]
    pending = [r for r in reminders if r.is_overdue]
    sent = [r for r in reminders if r.push_sent_at is not None]

    form = None
    if can_manage:
        if request.method == 'POST':
            form = ScheduleReminderForm(request.POST)
            if form.is_valid():
                reminder = form.save(commit=False)
                reminder.user = request.user
                reminder.save()
                messages.success(
                    request,
                    f'Đã tạo nhắc «{reminder.title}» lúc {timezone.localtime(reminder.remind_at):%H:%M %d/%m/%Y}.',
                )
                return redirect('utilities:schedule_reminder_home')
        else:
            form = ScheduleReminderForm()

    from utilities.push_service import webpush_configured
    from utilities.portal_push_eligibility import user_portal_push_eligible

    push_ready = webpush_configured() and user_portal_push_eligible(request.user)
    subscribed = False
    if push_ready:
        from utilities.models import MealPushSubscription
        subscribed = MealPushSubscription.objects.filter(user=request.user).exists()

    return render(request, 'utilities/schedule_reminder_home.html', {
        'form': form,
        'can_manage': can_manage,
        'upcoming': upcoming,
        'pending': pending,
        'sent': sent,
        'push_ready': push_ready,
        'push_subscribed': subscribed,
        'now': now,
    })


@module_perm_required(MODULE_UTILITIES, 'create')
@require_POST
def schedule_reminder_delete(request, pk):
    if not _can_manage_schedule_reminder(request.user):
        raise Http404
    reminder = get_object_or_404(ScheduleReminder, pk=pk, user=request.user)
    reminder.is_active = False
    reminder.save(update_fields=['is_active', 'updated_at'])
    messages.success(request, 'Đã xóa nhắc lịch.')
    return redirect('utilities:schedule_reminder_home')
