"""Xác minh thông tin khám sức khỏe — khớp mã NV, lưu phiếu, cập nhật hồ sơ."""

from __future__ import annotations

import re

from django.db import IntegrityError, transaction

from hrm.phone import format_phone_vn, is_valid_vn_mobile, normalize_phone

from .models import HealthCheckCampaign, HealthCheckPerson, HealthCheckSubmission

NOT_IN_LIST_MESSAGE = (
    'Anh/chị không có tên trong danh sách khám sức khỏe đợt này, '
    'không cần thực hiện thao tác xác minh'
)
OUTSIDE_WINDOW_MESSAGE = 'Bạn không được phép sử dụng tính năng này'
KSK_MANAGE_SLUGS = frozenset({'hcns-nhan-vien', 'hcns-truong-phong'})

ID_NUMBER_RE = re.compile(r'^\d{9}$|^\d{12}$')
# key, label, inputmode, autocomplete, placeholder
FIELD_SPECS = (
    ('personal', 'Cá nhân', (
        ('full_name', 'Họ và tên', 'text', 'name', ''),
        ('id_number', 'Số CMND/CCCD', 'numeric', 'off', '9 hoặc 12 chữ số'),
        ('phone', 'Số điện thoại', 'tel', 'tel', '0xxxxxxxxx'),
    )),
    ('address', 'Địa chỉ sau sáp nhập', (
        ('street', 'Số nhà, đường, ấp', 'text', 'street-address', 'Số nhà, tên đường, ấp'),
        ('ward', 'Phường/xã', 'text', 'off', 'Phường hoặc xã'),
        ('province', 'Tỉnh/thành phố', 'text', 'off', ''),
    )),
)
FIELD_LABELS = tuple(
    (key, label)
    for _section_id, _title, fields in FIELD_SPECS
    for key, label, *_rest in fields
)


def current_campaign():
    campaign = (
        HealthCheckCampaign.objects.filter(is_open=True).order_by('-created_at').first()
    )
    if campaign:
        return campaign
    return HealthCheckCampaign.objects.order_by('-created_at').first()


def person_for_profile(campaign, profile):
    code = ((profile.employee_code if profile else '') or '').strip()
    if not campaign or not code:
        return None
    return (
        campaign.people.filter(employee_code__iexact=code)
        .exclude(employee_code='')
        .first()
    )


UNCHANGED = '-'


def _compact(value) -> str:
    return ' '.join(str(value or '').split())


def _same_text(left, right) -> bool:
    return _compact(left).casefold() == _compact(right).casefold()


def _same_id(left, right) -> bool:
    digits_left = re.sub(r'\D', '', str(left or ''))
    digits_right = re.sub(r'\D', '', str(right or ''))
    if digits_left or digits_right:
        return digits_left == digits_right
    return _same_text(left, right)


def _same_phone(left, right) -> bool:
    left_key = normalize_phone(left)
    right_key = normalize_phone(right)
    if left_key or right_key:
        return left_key == right_key
    return _same_text(left, right)


def changed_or_dash(original, submitted, *, kind='text') -> str:
    """Giá trị mới nếu khác danh sách gốc, ngược lại dấu gạch."""
    if kind == 'phone':
        same = _same_phone(original, submitted)
        shown = display_phone(submitted)
    elif kind == 'id':
        same = _same_id(original, submitted)
        shown = _compact(submitted)
    else:
        same = _same_text(original, submitted)
        shown = _compact(submitted)
    if same:
        return UNCHANGED
    return shown or UNCHANGED


def changed_address_or_dash(original_street, original_ward, original_province, street, ward, province, *, sep=', ') -> str:
    same = (
        _same_text(original_street, street)
        and _same_text(original_ward, ward)
        and _same_text(original_province, province)
    )
    if same:
        return UNCHANGED
    parts = [_compact(street), _compact(ward), _compact(province)]
    text = sep.join(part for part in parts if part)
    return text or UNCHANGED


def display_phone(value: str) -> str:
    raw = (value or '').strip()
    if not raw:
        return ''
    normalized = normalize_phone(raw)
    if is_valid_vn_mobile(normalized):
        return format_phone_vn(normalized)
    return raw


def values_from_person(person) -> dict:
    return {
        'full_name': person.full_name or '',
        'id_number': person.id_number or '',
        'phone': display_phone(person.phone),
        'street': person.street or '',
        'ward': person.ward or '',
        'province': person.province or '',
    }


def values_from_submission(submission) -> dict:
    return {
        'full_name': submission.full_name,
        'id_number': submission.id_number,
        'phone': display_phone(submission.phone),
        'street': submission.street,
        'ward': submission.ward,
        'province': submission.province,
    }


def parse_posted(data) -> dict:
    return {
        key: (data.get(key) or '').strip()
        for key, _label in FIELD_LABELS
    }


def validate_values(values: dict) -> dict:
    errors = {}
    if not values['full_name']:
        errors['full_name'] = 'Nhập họ và tên.'
    id_number = re.sub(r'\s+', '', values['id_number'])
    values['id_number'] = id_number
    if not ID_NUMBER_RE.fullmatch(id_number):
        errors['id_number'] = 'Số CMND gồm 9 chữ số hoặc CCCD gồm 12 chữ số.'
    phone = normalize_phone(values['phone'])
    if not is_valid_vn_mobile(phone):
        errors['phone'] = 'Số điện thoại phải là số di động Việt Nam, 10 số.'
    else:
        values['phone'] = format_phone_vn(phone)
    if not values['street']:
        errors['street'] = 'Nhập số nhà, đường, ấp.'
    if not values['ward']:
        errors['ward'] = 'Nhập phường/xã.'
    if not values['province']:
        errors['province'] = 'Nhập tỉnh/thành phố.'
    return errors


def save_submission(*, user, profile, campaign, person, values: dict):
    """Lưu phiếu và cập nhật họ tên, SĐT trên hồ sơ Portal."""
    phone_stored = normalize_phone(values['phone'])
    with transaction.atomic():
        submission, _created = HealthCheckSubmission.objects.update_or_create(
            campaign=campaign,
            user=user,
            defaults={
                'person': person,
                'full_name': values['full_name'],
                'id_number': values['id_number'],
                'phone': format_phone_vn(phone_stored),
                'street': values['street'],
                'ward': values['ward'],
                'province': values['province'],
            },
        )
        if profile is not None:
            update_fields = []
            if (profile.full_name or '') != values['full_name']:
                profile.full_name = values['full_name']
                update_fields.append('full_name')
            if normalize_phone(profile.phone) != phone_stored:
                profile.phone = phone_stored
                update_fields.append('phone')
            if update_fields:
                try:
                    profile.save(update_fields=update_fields)
                except IntegrityError as exc:
                    raise ValueError(
                        'Số điện thoại này đã thuộc hồ sơ nhân viên khác.'
                    ) from exc
    return submission
