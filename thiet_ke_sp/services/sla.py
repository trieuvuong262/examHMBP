"""Hạn xử lý từng bước: số ngày chuẩn (cấu hình được) + giờ chốt hạn trong ngày."""

from __future__ import annotations

from datetime import datetime, time, timedelta

from django.utils import timezone

from thiet_ke_sp.models import ModuleSetting, ReceivingDepartment, Status

# (bước, nhãn, số ngày mặc định)
SLA_STEPS = (
    (Status.BRIEF_PENDING, 'Duyệt đề bài', 2),
    (Status.BRIEF_NEEDS_INFO, 'Bổ sung đề bài', 2),
    (Status.DESIGNING, 'Thiết kế / chỉnh thiết kế', 7),
    (Status.DESIGN_PENDING, 'Duyệt thiết kế', 2),
    (Status.SAMPLING, 'Làm mẫu / sửa mẫu', 7),
    (Status.SAMPLE_EVAL_PENDING, 'Đánh giá mẫu', 3),
    (Status.MASTER_PENDING, 'Duyệt mẫu chuẩn', 2),
    (Status.APPROVED, 'Bàn giao sản xuất', 2),
    (Status.HANDED_OVER, 'Bộ phận xác nhận nhận bàn giao', 2),
)
DEFAULT_SLA_DAYS = {step: days for step, _label, days in SLA_STEPS}
SLA_ALIASES = {
    Status.DESIGN_REVISE: Status.DESIGNING,
    Status.SAMPLE_REVISE: Status.SAMPLING,
}
DEFAULT_DUE_HOUR = 17


def get_settings() -> ModuleSetting:
    setting = ModuleSetting.objects.order_by('pk').first()
    if setting is None:
        setting = ModuleSetting.objects.create(sla_days=dict(DEFAULT_SLA_DAYS), due_hour=DEFAULT_DUE_HOUR)
    return setting


def sla_days(step: str, setting: ModuleSetting | None = None) -> int:
    setting = setting or get_settings()
    key = SLA_ALIASES.get(step, step)
    raw = (setting.sla_days or {}).get(key, DEFAULT_SLA_DAYS.get(key, 2))
    try:
        return max(int(raw), 0)
    except (TypeError, ValueError):
        return DEFAULT_SLA_DAYS.get(key, 2)


def due_at_for(step: str, *, start=None, setting: ModuleSetting | None = None) -> datetime:
    setting = setting or get_settings()
    start_date = timezone.localdate(start) if start else timezone.localdate()
    due_date = start_date + timedelta(days=sla_days(step, setting))
    hour = min(max(int(setting.due_hour or DEFAULT_DUE_HOUR), 0), 23)
    return timezone.make_aware(datetime.combine(due_date, time(hour, 0)))


def default_receiver_ids(setting: ModuleSetting | None = None) -> dict[str, int | None]:
    setting = setting or get_settings()
    raw = setting.default_receivers or {}
    result = {}
    for dept in ReceivingDepartment.values:
        try:
            result[dept] = int(raw.get(dept)) if raw.get(dept) else None
        except (TypeError, ValueError):
            result[dept] = None
    return result
