"""Xử lý từ chối đặt cơm / không ứng lương từ trang chủ."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from hrm.menu_permissions import user_can_create_menu
from hrm.module_permissions import MODULE_UTILITIES
from reports.report_profile import is_production_report_user

from utilities.meal_rules import current_orderable_meal_date, is_meal_order_window_open
from utilities.models import MealOrder, MealOrderDecline, SalaryAdvanceDecline, SalaryAdvanceRequest
from utilities.salary_rules import current_advance_month, is_salary_advance_open


@login_required
@require_POST
def meal_decline(request):
    if not user_can_create_menu(request.user, MODULE_UTILITIES, 'meal_ordering'):
        messages.error(request, 'Bạn không có quyền đặt cơm.')
        return redirect('home_portal')
    if not is_production_report_user(request.user):
        messages.error(request, 'Nhắc đặt cơm chỉ áp dụng phòng ban sản xuất.')
        return redirect('home_portal')

    meal_date = current_orderable_meal_date()
    if not meal_date or not is_meal_order_window_open(meal_date):
        messages.warning(request, 'Ngoài khung giờ đặt cơm (16:00–20:00).')
        return redirect('home_portal')

    if MealOrder.objects.filter(employee=request.user, meal_date=meal_date).exists():
        messages.info(request, 'Bạn đã đặt cơm cho ngày này.')
        return redirect('home_portal')

    MealOrderDecline.objects.get_or_create(
        employee=request.user,
        meal_date=meal_date,
    )
    messages.success(
        request,
        f'Đã ghi nhận bạn không đặt cơm ngày {meal_date.strftime("%d/%m/%Y")}.',
    )
    return redirect('home_portal')


@login_required
@require_POST
def salary_decline(request):
    if not user_can_create_menu(request.user, MODULE_UTILITIES, 'salary_advance'):
        messages.error(request, 'Bạn không có quyền ứng lương.')
        return redirect('home_portal')
    if not is_salary_advance_open():
        messages.warning(request, 'Ứng lương chỉ mở vào ngày 18 và 19 hàng tháng.')
        return redirect('home_portal')

    month = current_advance_month()
    if SalaryAdvanceRequest.objects.filter(employee=request.user, request_month=month).exists():
        messages.info(request, 'Bạn đã gửi yêu cầu ứng lương tháng này.')
        return redirect('home_portal')

    SalaryAdvanceDecline.objects.get_or_create(
        employee=request.user,
        request_month=month,
    )
    messages.success(
        request,
        f'Đã ghi nhận bạn không ứng lương tháng {month.strftime("%m/%Y")}.',
    )
    return redirect('home_portal')
