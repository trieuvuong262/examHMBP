"""Mốc «đã gửi» của báo cáo sản xuất.

Ca tối chạy qua nửa đêm nên giờ bấm gửi (05:00 hôm sau, hoặc giờ hệ thống tự
động gửi) không phản ánh đúng ca làm. Với ca tối, `submitted_at` lấy theo lúc
người dùng bấm bắt đầu công đoạn đầu tiên; giờ bấm gửi thật lưu ở
`submit_clicked_at` để hạn duyệt / hạn sửa vẫn tính như cũ.
"""

from __future__ import annotations

from reports.models import DailyWorkReport, ProductionShiftProduct


def is_night_shift_report(report) -> bool:
    if not getattr(report, 'is_production_report', False):
        return False
    return (getattr(report, 'shift', '') or '') == DailyWorkReport.SHIFT_NIGHT


def first_step_started_at(report):
    """Lúc bấm bắt đầu công đoạn đầu tiên — fallback về mốc bắt đầu ca."""
    if getattr(report, 'pk', None):
        started_at = (
            ProductionShiftProduct.objects.filter(
                report_id=report.pk,
                started_at__isnull=False,
            )
            .order_by('started_at')
            .values_list('started_at', flat=True)
            .first()
        )
        if started_at:
            return started_at
    return getattr(report, 'shift_started_at', None)


def resolve_submitted_at(report, clicked_at):
    """Giá trị ghi vào `submitted_at` khi báo cáo chuyển sang Đã gửi."""
    if not is_night_shift_report(report):
        return clicked_at
    return first_step_started_at(report) or clicked_at


def submit_anchor_at(report):
    """Mốc tính hạn duyệt / hạn sửa — giờ bấm gửi thật."""
    return getattr(report, 'submit_clicked_at', None) or getattr(report, 'submitted_at', None)
