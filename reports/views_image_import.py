"""Upload/review ảnh phiếu SX trước khi đổ dữ liệu vào Nhập hộ."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_REPORTS
from hrm.permissions import can_view_team_reports, get_team_report_members
from reports.models import DailyWorkReport, ProductionReportImageImport
from reports.production_hourly import can_proxy_enter_daily_report
from reports.production_report_image_ai import (
    ProductionReportImageAIError,
    extract_production_report_image,
)
from reports.production_shift_policy import shift_display_label
from reports.production_slots import normalize_shift
from reports.report_profile import REPORT_PROFILE_PRODUCTION

User = get_user_model()
MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}


def _parse_report_date(request):
    raw = (request.POST.get('date') or request.GET.get('date') or '').strip()
    if raw:
        try:
            return datetime.strptime(raw[:10], '%Y-%m-%d').date()
        except ValueError:
            pass
    return timezone.localdate()


def _parse_shift(request) -> str:
    raw = (
        request.POST.get('shift')
        or request.GET.get('shift')
        or DailyWorkReport.SHIFT_MORNING
    ).strip().upper()
    shift = normalize_shift(raw) if raw else DailyWorkReport.SHIFT_MORNING
    if shift not in (DailyWorkReport.SHIFT_MORNING, DailyWorkReport.SHIFT_NIGHT):
        return DailyWorkReport.SHIFT_MORNING
    return shift


def _eligible_members(viewer):
    return (
        get_team_report_members(viewer)
        .filter(profile__department__report_profile=REPORT_PROFILE_PRODUCTION)
        .select_related('profile', 'profile__department', 'profile__division')
        .order_by('profile__full_name', 'username')
    )


def _subject_or_none(viewer, raw_id):
    try:
        subject = _eligible_members(viewer).get(pk=int(raw_id))
    except (User.DoesNotExist, TypeError, ValueError):
        return None
    return subject if can_proxy_enter_daily_report(viewer, subject) else None


def _image_error(upload) -> str:
    if not upload:
        return 'Chọn ảnh phiếu báo cáo trước khi phân tích.'
    suffix = Path(getattr(upload, 'name', '') or '').suffix.lower()
    content_type = (getattr(upload, 'content_type', '') or '').lower()
    if suffix not in IMAGE_EXTENSIONS or not content_type.startswith('image/'):
        return 'Chỉ nhận ảnh JPG, PNG hoặc WebP.'
    if getattr(upload, 'size', 0) > MAX_IMAGE_BYTES:
        return 'Ảnh tối đa 10 MB.'
    return ''


def _member_label(member) -> str:
    if not member:
        return 'Chưa khớp công nhân'
    profile = getattr(member, 'profile', None)
    return profile.full_name if profile and profile.full_name else member.username


def _norm_code(value: str) -> str:
    return re.sub(r'[\s\-_.]', '', (value or '').strip()).upper()


def _norm_name(value: str) -> str:
    text = unicodedata.normalize('NFKD', (value or '').strip().lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r'\s+', ' ', text)


def _match_member_from_extracted(members, extracted: dict):
    """Khớp CN theo mã NV trước, rồi họ tên. Trả (member|None, reason)."""
    code = _norm_code(str((extracted or {}).get('employee_code') or ''))
    name = _norm_name(str((extracted or {}).get('employee_name') or ''))

    if code:
        code_hits = []
        for member in members:
            profile = getattr(member, 'profile', None)
            member_code = _norm_code(getattr(profile, 'employee_code', '') or '')
            if member_code and member_code == code:
                code_hits.append(member)
        if len(code_hits) == 1:
            return code_hits[0], f'Khớp mã NV {code_hits[0].profile.employee_code}'
        if len(code_hits) > 1:
            return None, f'Mã NV {code} khớp nhiều người trong đội — chọn thủ công.'

    if name:
        exact = []
        for member in members:
            profile = getattr(member, 'profile', None)
            full_name = _norm_name(getattr(profile, 'full_name', '') or '')
            username = _norm_name(member.username or '')
            if name and name in (full_name, username):
                exact.append(member)
        if len(exact) == 1:
            return exact[0], f'Khớp họ tên “{_member_label(exact[0])}”'
        if len(exact) > 1:
            return None, f'Họ tên “{(extracted or {}).get("employee_name")}” khớp nhiều người — chọn thủ công.'

        partial = []
        for member in members:
            profile = getattr(member, 'profile', None)
            full_name = _norm_name(getattr(profile, 'full_name', '') or '')
            if full_name and (name in full_name or full_name in name):
                partial.append(member)
        if len(partial) == 1:
            return partial[0], f'Khớp gần đúng họ tên “{_member_label(partial[0])}”'
        if len(partial) > 1:
            return None, 'Họ tên trên phiếu khớp nhiều người trong đội — chọn thủ công.'

    if code or name:
        return None, 'Không tìm thấy công nhân trong đội khớp mã/tên trên phiếu.'
    return None, 'AI không đọc được mã NV/họ tên trên phiếu.'


def _can_access_import(viewer, record) -> bool:
    if not can_view_team_reports(viewer):
        return False
    if record.created_by_id and record.created_by_id != viewer.id and not viewer.is_superuser:
        return False
    if record.employee_id and not can_proxy_enter_daily_report(viewer, record.employee):
        return False
    return True


@module_perm_required(MODULE_REPORTS, 'view')
def production_report_image_import(request):
    """Upload ảnh (+ ngày/ca); AI đọc mã/tên CN rồi tự khớp trong đội."""
    if not can_view_team_reports(request.user):
        messages.error(request, 'Bạn không có quyền import ảnh báo cáo.')
        return redirect('home_portal')

    report_date = _parse_report_date(request)
    shift = _parse_shift(request)
    members = list(_eligible_members(request.user))
    if not members:
        messages.info(request, 'Không có công nhân sản xuất cấp dưới để import báo cáo.')
        return redirect('reports:team_cn')

    if request.method == 'POST':
        # for_user chỉ còn là override tùy chọn (ẩn), mặc định để AI khớp.
        subject = _subject_or_none(request.user, request.POST.get('for_user'))
        image = request.FILES.get('image')
        error = _image_error(image)
        if error:
            messages.error(request, error)
        else:
            record = ProductionReportImageImport.objects.create(
                employee=subject,
                report_date=report_date,
                shift=shift,
                image=image,
                original_name=(getattr(image, 'name', '') or '')[:255],
                created_by=request.user,
            )
            try:
                record.extracted_data = extract_production_report_image(record.image)
                record.status = ProductionReportImageImport.STATUS_READY
                if not record.employee_id:
                    matched, reason = _match_member_from_extracted(
                        members, record.extracted_data,
                    )
                    if matched:
                        record.employee = matched
                        warnings = list((record.extracted_data or {}).get('warnings') or [])
                        warnings.insert(0, f'Đã tự gắn công nhân: {reason}.')
                        record.extracted_data = {
                            **(record.extracted_data or {}),
                            'warnings': warnings,
                            'matched_by': reason,
                        }
                    else:
                        warnings = list((record.extracted_data or {}).get('warnings') or [])
                        warnings.insert(0, reason)
                        record.extracted_data = {
                            **(record.extracted_data or {}),
                            'warnings': warnings,
                            'matched_by': '',
                        }
                record.save(update_fields=['extracted_data', 'status', 'employee', 'updated_at'])
            except ProductionReportImageAIError as exc:
                record.status = ProductionReportImageImport.STATUS_FAILED
                record.error_message = str(exc)[:500]
                record.save(update_fields=['status', 'error_message', 'updated_at'])
                messages.error(request, record.error_message)
                return redirect('reports:production_image_import')
            if record.employee_id:
                messages.success(
                    request,
                    f'AI đã đọc ảnh và gắn {_member_label(record.employee)}. Kiểm tra trước khi đổ vào Nhập hộ.',
                )
            else:
                messages.warning(
                    request,
                    'AI đã đọc ảnh nhưng chưa khớp được công nhân. Chọn CN trên trang kiểm tra.',
                )
            return redirect('reports:production_image_import_review', pk=record.pk)

    return render(request, 'reports/production_image_import.html', {
        'members': members,
        'report_date': report_date,
        'shift': shift,
        'shift_label': shift_display_label(shift),
        'back_url': reverse('reports:team_cn') + f'?date={report_date.isoformat()}',
    })


@module_perm_required(MODULE_REPORTS, 'view')
def production_report_image_import_review(request, pk):
    """Review AI extraction rồi chuyển sang form Nhập hộ để xác nhận/lưu."""
    record = get_object_or_404(
        ProductionReportImageImport.objects.select_related(
            'employee',
            'employee__profile',
            'employee__profile__department',
            'employee__profile__division',
        ),
        pk=pk,
    )
    if not _can_access_import(request.user, record):
        messages.error(request, 'Bạn không có quyền xem import ảnh này.')
        return redirect('reports:team_cn')

    members = list(_eligible_members(request.user))

    if request.method == 'POST' and request.POST.get('action') == 'assign_worker':
        subject = _subject_or_none(request.user, request.POST.get('for_user'))
        if not subject:
            messages.error(request, 'Chọn một công nhân hợp lệ trong đội.')
        else:
            record.employee = subject
            warnings = [
                w for w in ((record.extracted_data or {}).get('warnings') or [])
                if 'chọn thủ công' not in w.lower()
                and 'không tìm thấy' not in w.lower()
                and 'không đọc được' not in w.lower()
                and 'khớp nhiều' not in w.lower()
            ]
            warnings.insert(0, f'Đã chọn thủ công: {_member_label(subject)}.')
            record.extracted_data = {
                **(record.extracted_data or {}),
                'warnings': warnings,
                'matched_by': 'Chọn thủ công trên trang kiểm tra',
            }
            record.save(update_fields=['employee', 'extracted_data', 'updated_at'])
            messages.success(request, f'Đã gắn công nhân {_member_label(subject)}.')
        return redirect('reports:production_image_import_review', pk=record.pk)

    data = record.extracted_data or {}
    proxy_url = ''
    if record.employee_id:
        proxy_url = (
            f"{reverse('reports:proxy_cn')}?date={record.report_date.isoformat()}"
            f"&for_user={record.employee_id}&shift={record.shift}&ai_import={record.pk}"
        )
    return render(request, 'reports/production_image_import_review.html', {
        'record': record,
        'data': data,
        'sessions': data.get('sessions') or [],
        'warnings': data.get('warnings') or [],
        'members': members,
        'needs_worker': record.employee_id is None,
        'subject_name': _member_label(record.employee),
        'shift_label': shift_display_label(record.shift),
        'proxy_url': proxy_url,
        'retry_url': reverse('reports:production_image_import'),
    })
