"""Trạng thái thử việc — tự tắt sau 2 tháng kể từ ngày vào làm."""
from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

PROBATION_MONTHS = 2


def probation_end_date(join_date: date | None) -> date | None:
    if not join_date:
        return None
    return join_date + relativedelta(months=PROBATION_MONTHS)


def probation_expired(join_date: date | None, *, today: date | None = None) -> bool:
    end = probation_end_date(join_date)
    if end is None:
        return False
    today = today or date.today()
    return today >= end


def resolve_on_probation(join_date: date | None, requested: bool, *, today: date | None = None) -> bool:
    """Giá trị lưu DB: không cho bật thử việc nếu đã quá hạn."""
    if probation_expired(join_date, today=today):
        return False
    return bool(requested)


def sync_probation_status(profile, *, today: date | None = None) -> bool:
    """Tắt thử việc khi đủ 2 tháng từ ngày vào. Trả về True nếu đã đổi."""
    if not profile.on_probation:
        return False
    if probation_expired(profile.join_date, today=today):
        profile.on_probation = False
        return True
    return False


def bulk_clear_expired_probation() -> int:
    """Cập nhật hàng loạt NV hết hạn thử việc. Trả về số bản ghi đã tắt."""
    from hrm.models import Profile

    today = date.today()
    expired_ids: list[int] = []
    for pk, join_date in (
        Profile.objects.filter(on_probation=True, join_date__isnull=False)
        .values_list('pk', 'join_date')
        .iterator(chunk_size=500)
    ):
        if probation_expired(join_date, today=today):
            expired_ids.append(pk)
    if not expired_ids:
        return 0
    return Profile.objects.filter(pk__in=expired_ids).update(on_probation=False)
