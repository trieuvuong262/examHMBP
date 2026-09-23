"""Mức đài thọ Company Trip, tính đến ngày khởi hành chứ không phải ngày đăng ký."""

from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from company_trip.constants import TRIP_START
from hrm.probation import probation_expired

TOUR_PRICE = 2_600_000
HALF_PRICE = TOUR_PRICE // 2
PROBATION_DAYS_FOR_HALF = 21
AS_OF_LABEL = '22/11/2026'


def _vnd(amount: int) -> str:
    return f'{amount:,}'.replace(',', '.') + ' đồng'


def _tenure_at_least_one_year(join_date: date, as_of: date) -> bool:
    return join_date <= as_of - relativedelta(years=1)


def assess_trip_fee(join_date: date | None, *, as_of: date | None = None) -> dict:
    """Trả về nội dung popup. Nhân viên chính thức đến ngày khởi hành không phải đóng."""
    as_of = as_of or TRIP_START
    if join_date is None:
        unknown = (
            f'Hồ sơ nhân sự chưa có ngày vào làm, nên chưa xác định được mức đài thọ '
            f'tính đến ngày khởi hành {AS_OF_LABEL}.'
        )
        return {
            'employee_charge': True,
            'employee_message': unknown,
            'relative_charge': True,
            'relative_message': unknown,
        }

    days = (as_of - join_date).days
    if probation_expired(join_date, today=as_of):
        employee_charge = False
        employee_message = ''
    elif days > PROBATION_DAYS_FOR_HALF:
        employee_charge = True
        employee_message = (
            f'Tính đến ngày khởi hành {AS_OF_LABEL}, bạn là nhân viên thử việc trên 3 tuần. '
            f'Công ty đài thọ 50% chi phí. Bạn cần đóng {_vnd(HALF_PRICE)} '
            f'(giá tour {_vnd(TOUR_PRICE)}/người).'
        )
    else:
        employee_charge = True
        employee_message = (
            f'Tính đến ngày khởi hành {AS_OF_LABEL}, thời gian thử việc của bạn chưa đủ 3 tuần. '
            f'Bạn không thuộc nhóm công ty đài thọ 100% hoặc 50%.'
        )

    if _tenure_at_least_one_year(join_date, as_of):
        relative_message = (
            f'Người thân đi cùng: thâm niên của bạn tính đến {AS_OF_LABEL} từ 1 năm trở lên. '
            f'Công ty đài thọ 50% chi phí người thân đầu tiên. Phần cần đóng: {_vnd(HALF_PRICE)} '
            f'(giá tour {_vnd(TOUR_PRICE)}/người). '
            f'Người thân thứ hai trở đi tự túc {_vnd(TOUR_PRICE)}.'
        )
    else:
        relative_message = (
            f'Người thân đi cùng: thâm niên của bạn tính đến {AS_OF_LABEL} chưa đủ 1 năm. '
            f'Chi phí người thân tự túc {_vnd(TOUR_PRICE)}.'
        )

    return {
        'employee_charge': employee_charge,
        'employee_message': employee_message,
        'relative_charge': True,
        'relative_message': relative_message,
    }
