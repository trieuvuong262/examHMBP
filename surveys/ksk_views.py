import io
from datetime import datetime

import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Subquery
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from openpyxl.styles import Font

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_SURVEYS
from hrm.permissions import get_profile

from .ksk import (
    FIELD_SPECS,
    NOT_IN_LIST_MESSAGE,
    OUTSIDE_WINDOW_MESSAGE,
    current_campaign,
    parse_posted,
    person_for_profile,
    save_submission,
    validate_values,
    values_from_person,
    values_from_submission,
)
from .models import HealthCheckSubmission


def _form_context(*, campaign, person, values, errors, submitted):
    """Nhóm trường theo FIELD_SPECS — không dùng FIELD_LABELS."""
    sections = []
    for section_id, title, specs in FIELD_SPECS:
        sections.append({
            'id': section_id,
            'title': title,
            'fields': [
                {
                    'key': key,
                    'label': label,
                    'inputmode': inputmode,
                    'autocomplete': autocomplete,
                    'placeholder': placeholder,
                    'value': values.get(key, ''),
                    'error': errors.get(key, ''),
                }
                for key, label, inputmode, autocomplete, placeholder in specs
            ],
        })
    return {
        'campaign': campaign,
        'person': person,
        'sections': sections,
        'errors': errors,
        'submitted': submitted,
        'can_edit': campaign.allows_update(),
    }


def _window_inputs(campaign):
    def _value(moment):
        if not moment:
            return ''
        return timezone.localtime(moment).strftime('%Y-%m-%dT%H:%M')

    if campaign is None:
        return '', ''
    return _value(campaign.opens_at), _value(campaign.closes_at)


@login_required
def health_check_update(request):
    campaign = current_campaign()
    if campaign is None or not campaign.allows_update():
        return render(request, 'surveys/ksk_not_in_list.html', {
            'message': OUTSIDE_WINDOW_MESSAGE,
            'campaign': campaign,
        })
    profile = get_profile(request.user)
    person = person_for_profile(campaign, profile)
    if person is None:
        return render(request, 'surveys/ksk_not_in_list.html', {
            'message': NOT_IN_LIST_MESSAGE,
            'campaign': campaign,
        })

    submission = HealthCheckSubmission.objects.filter(
        campaign=campaign,
        user=request.user,
    ).first()
    baseline = values_from_submission(submission) if submission else values_from_person(person)
    errors = {}

    if request.method == 'POST':
        if not campaign.allows_update():
            messages.error(request, OUTSIDE_WINDOW_MESSAGE)
            return redirect('surveys:ksk_update')
        values = parse_posted(request.POST)
        errors = validate_values(values)
        if not errors:
            try:
                save_submission(
                    user=request.user,
                    profile=profile,
                    campaign=campaign,
                    person=person,
                    values=values,
                )
            except ValueError as exc:
                errors = {'phone': str(exc)}
            else:
                messages.success(request, 'Đã lưu thông tin xác minh.')
                return redirect('surveys:ksk_update')
        baseline = values

    return render(request, 'surveys/ksk_update.html', _form_context(
        campaign=campaign,
        person=person,
        values=baseline,
        errors=errors,
        submitted=submission is not None and not errors,
    ))


@module_perm_required(MODULE_SURVEYS, 'view')
def health_check_results(request):
    campaign = current_campaign()
    status = (request.GET.get('trang-thai') or '').strip()
    if status not in {'confirmed', 'pending'}:
        status = ''
    people = []
    confirmed_count = 0
    if campaign is not None:
        latest = HealthCheckSubmission.objects.filter(
            campaign=campaign,
            person_id=OuterRef('pk'),
        )
        people_qs = campaign.people.annotate(
            submitted_name=Subquery(latest.values('full_name')[:1]),
            submitted_id=Subquery(latest.values('id_number')[:1]),
            submitted_phone=Subquery(latest.values('phone')[:1]),
            submitted_street=Subquery(latest.values('street')[:1]),
            submitted_ward=Subquery(latest.values('ward')[:1]),
            submitted_province=Subquery(latest.values('province')[:1]),
            submitted_at=Subquery(latest.values('updated_at')[:1]),
        ).order_by('sort_order')
        confirmed_count = campaign.submissions.count()
        if status == 'confirmed':
            people_qs = people_qs.filter(submitted_at__isnull=False)
        elif status == 'pending':
            people_qs = people_qs.filter(submitted_at__isnull=True)
        people = list(people_qs)
    return render(request, 'surveys/ksk_results.html', {
        'campaign': campaign,
        'people': people,
        'status': status,
        'confirmed_count': confirmed_count,
        'total_count': campaign.people.count() if campaign else 0,
        'opens_value': _window_inputs(campaign)[0],
        'closes_value': _window_inputs(campaign)[1],
        'window_open': campaign.allows_update() if campaign else False,
    })


@module_perm_required(MODULE_SURVEYS, 'update')
@require_POST
def health_check_schedule(request):
    campaign = current_campaign()
    if campaign is None:
        messages.error(request, 'Chưa có danh sách khám sức khỏe.')
        return redirect('surveys:ksk_results')
    opens_at = _parse_local_datetime(request.POST.get('opens_at'))
    closes_at = _parse_local_datetime(request.POST.get('closes_at'))
    if opens_at is None or closes_at is None:
        messages.error(request, 'Nhập đủ thời gian bắt đầu và kết thúc.')
        return redirect('surveys:ksk_results')
    if closes_at <= opens_at:
        messages.error(request, 'Thời gian kết thúc phải sau thời gian bắt đầu.')
        return redirect('surveys:ksk_results')
    campaign.opens_at = opens_at
    campaign.closes_at = closes_at
    campaign.save(update_fields=['opens_at', 'closes_at'])
    messages.success(request, 'Đã lưu thời gian được phép cập nhật.')
    return redirect('surveys:ksk_results')


def _parse_local_datetime(raw):
    text = (raw or '').strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


@module_perm_required(MODULE_SURVEYS, 'view')
def health_check_export(request):
    campaign = current_campaign()
    rows = []
    if campaign is not None:
        submissions = {
            item.person_id: item
            for item in campaign.submissions.select_related('person')
        }
        for person in campaign.people.order_by('sort_order'):
            saved = submissions.get(person.pk)
            rows.append({
                'STT': person.sort_order,
                'MÃ NHÂN VIÊN': person.employee_code,
                'HỌ VÀ TÊN': saved.full_name if saved else person.full_name,
                'Số CMND/CCCD': saved.id_number if saved else person.id_number,
                'SỐ ĐIỆN THOẠI': saved.phone if saved else person.phone,
                'ĐỊA CHỈ: SỐ NHÀ, ĐƯỜNG, ẤP… SAU SÁP NHẬP': saved.street if saved else person.street,
                'ĐẠI CHỈ: PHƯỜNG/XÃ SAU SÁP NHẬP': saved.ward if saved else person.ward,
                'TỈNH/THÀNH PHỐ': saved.province if saved else person.province,
            })
    if not rows:
        rows = [{'STT': '', 'MÃ NHÂN VIÊN': '', 'HỌ VÀ TÊN': ''}]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        frame = pd.DataFrame(rows)
        frame.to_excel(writer, index=False, sheet_name='Sheet1')
        sheet = writer.sheets['Sheet1']
        for cell in sheet[1]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = 28
    stamp = datetime.now().strftime('%Y%m%d')
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename=DS-KSK_{stamp}.xlsx'
    return response
