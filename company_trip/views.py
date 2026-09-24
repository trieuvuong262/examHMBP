from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from company_trip.constants import (
    DEFAULT_PICKUP_POINT,
    ROOM_CHOICES,
    ROOM_COLLEAGUE,
    ROOM_ORGANIZER,
    ROOM_RELATIVE,
    STATUS_CANCELLED,
    STATUS_REGISTERED,
)
from company_trip.fees import assess_trip_fee
from company_trip.access import (
    TRIP_MANAGE_ACTIONS,
    TRIP_OPEN_ACTIONS,
    trip_can_create,
    trip_ui_flags,
)
from company_trip.decorators import trip_perm_required
from company_trip.phones import domestic_phone
from company_trip.relatives import replace_registration_relatives
from company_trip.email_service import (
    _companion_names_for,
    render_trip_message,
    send_companion_invite,
    send_registration_invites,
    send_trip_email,
)
from company_trip.excel_export import export_registrations_xlsx
from company_trip.forms import TripEmailTemplateForm, TripRegistrationForm, TripSettingsForm
from company_trip.models import TripEmailTemplate, TripRegistration, TripSettings
from company_trip.rooms import apply_companions_on_register, clear_room_key
from hrm.permissions import get_profile
from hrm.models import Profile
from PortalJustPlay.list_search import apply_term_search, get_search_query
from PortalJustPlay.pagination import paginate_queryset


def _profile_can_register(profile) -> tuple[bool, str]:
    if not profile:
        return False, 'Không tìm thấy hồ sơ nhân sự.'
    if not profile.is_employed:
        return False, 'Tài khoản không còn đang làm việc — không thể đăng ký.'
    if not profile.user.is_active:
        return False, 'Tài khoản đã bị khóa.'
    settings_obj = TripSettings.load()
    if not settings_obj.registration_open:
        return False, 'Đăng ký Company Trip đã đóng.'
    return True, ''


def _colleague_invite(profile):
    """Bản đăng ký đồng nghiệp mà hồ sơ này được chọn, chưa phải người điền form."""
    if not profile:
        return None
    return (
        TripRegistration.objects.filter(
            companion1=profile,
            status=STATUS_REGISTERED,
            room_type=ROOM_COLLEAGUE,
        )
        .select_related('profile', 'companion1', 'companion1__user')
        .first()
    )


def _save_profile_email_if_empty(profile, email: str, *, overwrite: bool = False) -> str:
    """Ghi email vào tài khoản nhân sự. Trả về lỗi nếu không ghi được."""
    email = (email or '').strip()
    if not email or not profile or not getattr(profile, 'user_id', None):
        return ''
    user = profile.user
    current = (user.email or '').strip()
    if current and not overwrite:
        return ''
    if current.lower() == email.lower():
        return ''
    User = user.__class__
    if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        return 'Email này đã thuộc hồ sơ nhân sự khác.'
    user.email = email
    user.save(update_fields=['email'])
    return ''


def _fee_notice(profile, *, show_on_load=False, room_select_id='') -> dict:
    assessed = assess_trip_fee(getattr(profile, 'join_date', None) if profile else None)
    return {
        'showOnLoad': show_on_load,
        'roomSelectId': room_select_id,
        'roomColleague': ROOM_COLLEAGUE,
        'roomRelative': ROOM_RELATIVE,
        'roomOrganizer': ROOM_ORGANIZER,
        'employeeCharge': assessed['employee_charge'],
        'employeeMessage': assessed['employee_message'],
        'relativeCharge': assessed['relative_charge'],
        'relativeMessage': assessed['relative_message'],
    }


def _snapshot_from_profile(profile) -> dict:
    return {
        'full_name': profile.full_name or profile.user.get_full_name() or profile.user.username,
        'email': profile.user.email or '',
        'phone': domestic_phone(profile.phone),
        'gender': profile.gender or '',
        'department_name': profile.department.name if profile.department_id else '',
        'date_of_birth': profile.date_of_birth,
    }


@trip_perm_required(*TRIP_OPEN_ACTIONS)
def hub(request):
    return redirect('company_trip:register')


@trip_perm_required(*TRIP_OPEN_ACTIONS)
def register(request):
    profile = get_profile(request.user)
    ok, reason = _profile_can_register(profile)
    settings_obj = TripSettings.load()

    existing = None
    if profile:
        existing = TripRegistration.objects.filter(profile=profile).first()

    if existing and existing.status == STATUS_REGISTERED:
        return render(request, 'company_trip/thank_you.html', {
            'already_submitted': True,
            'settings': settings_obj,
            'registration': existing,
            'room_colleague': ROOM_COLLEAGUE,
            'room_relative': ROOM_RELATIVE,
            **trip_ui_flags(request.user),
        })

    invite = _colleague_invite(profile)
    if invite:
        snapshot = _snapshot_from_profile(profile)
        invite_email_value = ''
        email_error = ''
        if request.method == 'POST' and request.POST.get('action') == 'confirm_companion':
            if not trip_can_create(request.user):
                messages.error(request, 'Bạn không có quyền đăng ký du lịch.')
                return redirect('company_trip:register')
            invite_email_value = (request.POST.get('invite_email') or '').strip()
            profile_email = (snapshot['email'] or '').strip()
            if invite_email_value:
                try:
                    validate_email(invite_email_value)
                except ValidationError:
                    email_error = 'Email không hợp lệ.'
                if not email_error and invite_email_value.lower() != profile_email.lower():
                    email_error = _save_profile_email_if_empty(
                        profile, invite_email_value, overwrite=bool(profile_email),
                    )
                    if not email_error:
                        snapshot['email'] = invite_email_value
                        profile_email = invite_email_value
            mailed = False
            if not email_error:
                if not invite.companion_confirmed:
                    invite.companion_confirmed = True
                    invite.companion_confirmed_at = timezone.now()
                    invite.save(update_fields=[
                        'companion_confirmed', 'companion_confirmed_at', 'updated_at',
                    ])
                target = invite_email_value or profile_email
                previous = (invite.companion_email or '').strip()
                if target and target.lower() != previous.lower():
                    mailed = send_companion_invite(invite, target, request=request)
                    if not mailed:
                        email_error = (
                            'Không gửi được thư tới email này. '
                            'Hộp thư có thể không tồn tại — hãy nhập email khác.'
                        )
                else:
                    mailed = True
            if not email_error and mailed:
                messages.success(request, 'Đã xác nhận đăng ký cùng đồng nghiệp.')
                return redirect('company_trip:register')
            invite.refresh_from_db()
        return render(request, 'company_trip/confirm_companion.html', {
            'settings': settings_obj,
            'registration': invite,
            'snapshot': snapshot,
            'invite_email_value': invite_email_value,
            'email_error': email_error,
            'fee_notice': _fee_notice(profile, show_on_load=True),
            **trip_ui_flags(request.user),
        })

    if not ok:
        return render(request, 'company_trip/closed.html', {
            'reason': reason,
            'settings': settings_obj,
        })

    if request.method == 'POST':
        if not trip_can_create(request.user):
            messages.error(request, 'Bạn không có quyền đăng ký du lịch.')
            return redirect('company_trip:register')
        form = TripRegistrationForm(
            request.POST,
            current_profile=profile,
            current_registration=existing,
        )
        if form.is_valid():
            if _colleague_invite(profile):
                messages.info(request, 'Đồng nghiệp đã đăng ký cho bạn. Vui lòng xác nhận thông tin.')
                return redirect('company_trip:register')
            snap = _snapshot_from_profile(profile)
            reg = existing or TripRegistration(profile=profile, user=request.user)
            for k, v in snap.items():
                setattr(reg, k, v)
            phone = form.cleaned_data.get('phone') or snap['phone']
            reg.phone = phone
            reg.room_type = form.cleaned_data['room_type']
            reg.bed_type = form.cleaned_data.get('bed_type') or ''
            reg.pickup_point = DEFAULT_PICKUP_POINT
            reg.note = form.cleaned_data.get('note') or ''
            reg.vegetarian = 'Không ăn chay'
            reg.allergy_note = ''
            reg.breakfast_choice = 'Không ăn sáng'
            reg.route = ''
            reg.detail_route = ''
            reg.shopping = 'Tham gia'
            reg.companion1 = form.cleaned_data.get('companion1_obj')
            reg.companion2 = None
            reg.companion_confirmed = False
            reg.companion_confirmed_at = None
            reg.companion_email = ''
            typed_email = (form.cleaned_data.get('invite_email') or '').strip()
            if not (snap.get('email') or '').strip() and typed_email:
                email_error = _save_profile_email_if_empty(profile, typed_email)
                if email_error:
                    form.add_error('invite_email', email_error)
                else:
                    reg.email = typed_email
            if not form.errors:
                people = form.cleaned_data.get('relatives') or []
                first = people[0] if people else {}
                reg.relative_full_name = first.get('full_name') or ''
                reg.relative_cccd = first.get('cccd') or ''
                reg.relative_phone = first.get('phone') or ''
                reg.relative_gender = first.get('gender') or ''
                reg.relative_date_of_birth = first.get('date_of_birth')
                reg.organized_committee = form.cleaned_data.get('organized_committee', False)
                reg.status = STATUS_REGISTERED
                reg.save()
                apply_companions_on_register(reg)
                if reg.room_type == ROOM_RELATIVE:
                    replace_registration_relatives(reg, people)

                send_registration_invites(reg, request=request)
                messages.success(request, 'Đăng ký Company Trip thành công.')
                return redirect('company_trip:thank_you')
    else:
        valid_rooms = {value for value, _label in ROOM_CHOICES}
        room_initial = existing.room_type if existing and existing.room_type in valid_rooms else None
        initial = {
            'phone': domestic_phone(profile.phone),
            'room_type': room_initial,
            'bed_type': existing.bed_type if existing else '',
            'pickup_point': DEFAULT_PICKUP_POINT,
        }
        if existing and existing.room_type == ROOM_RELATIVE:
            stored = list(existing.relatives.all())
            if stored:
                initial['relatives'] = [
                    {
                        'full_name': item.full_name,
                        'cccd': item.cccd,
                        'phone': item.phone,
                        'gender': item.gender,
                        'date_of_birth': item.date_of_birth,
                    }
                    for item in stored
                ]
            elif existing.relative_full_name:
                initial['relatives'] = [{
                    'full_name': existing.relative_full_name,
                    'cccd': existing.relative_cccd,
                    'phone': existing.relative_phone,
                    'gender': existing.relative_gender,
                    'date_of_birth': existing.relative_date_of_birth,
                }]
        if existing and existing.room_type == ROOM_COLLEAGUE and existing.companion1_id:
            initial['companion1_id'] = existing.companion1_id
        form = TripRegistrationForm(
            initial=initial,
            current_profile=profile,
            current_registration=existing,
        )

    companion_prefill_name = ''
    companion_id = None
    if request.method == 'POST':
        raw_companion = (request.POST.get('companion1_id') or '').strip()
        if raw_companion.isdigit():
            companion_id = int(raw_companion)
    elif existing and existing.room_type == ROOM_COLLEAGUE and existing.companion1_id:
        companion_id = existing.companion1_id
    if companion_id:
        companion_prefill_name = (
            Profile.objects.filter(pk=companion_id).values_list('full_name', flat=True).first() or ''
        )

    return render(request, 'company_trip/register.html', {
        'form': form,
        'settings': settings_obj,
        'profile': profile,
        'snapshot': _snapshot_from_profile(profile),
        'room_colleague': ROOM_COLLEAGUE,
        'room_relative': ROOM_RELATIVE,
        'companion_prefill_name': companion_prefill_name,
        'fee_notice': _fee_notice(profile, room_select_id=form['room_type'].id_for_label),
        **trip_ui_flags(request.user),
    })


@trip_perm_required(*TRIP_OPEN_ACTIONS)
def thank_you(request):
    profile = get_profile(request.user)
    reg = TripRegistration.objects.filter(profile=profile, status=STATUS_REGISTERED).first() if profile else None
    return render(request, 'company_trip/thank_you.html', {
        'already_submitted': False,
        'settings': TripSettings.load(),
        'registration': reg,
        'room_colleague': ROOM_COLLEAGUE,
        'room_relative': ROOM_RELATIVE,
        **trip_ui_flags(request.user),
    })


@require_GET
@trip_perm_required(*TRIP_OPEN_ACTIONS)
def companion_search(request):
    q = (request.GET.get('q') or '').strip()
    if len(q) < 1:
        return JsonResponse([], safe=False)
    exclude_raw = request.GET.get('exclude') or ''
    exclude_ids = [int(x) for x in exclude_raw.split(',') if x.strip().isdigit()]
    qs = Profile.objects.filter(is_employed=True, user__is_active=True).select_related(
        'user', 'department',
    )
    if exclude_ids:
        qs = qs.exclude(pk__in=exclude_ids)
    qs = qs.filter(
        Q(full_name__icontains=q)
        | Q(user__username__icontains=q)
        | Q(employee_code__icontains=q)
        | Q(job_position__icontains=q)
    )
    busy_profile_ids = set(
        TripRegistration.objects.filter(status=STATUS_REGISTERED).values_list('profile_id', flat=True)
    )
    busy_companion_ids = set(
        TripRegistration.objects.filter(
            status=STATUS_REGISTERED,
            room_type=ROOM_COLLEAGUE,
            companion1_id__isnull=False,
        ).values_list('companion1_id', flat=True)
    )
    results = []
    for p in qs.order_by('full_name')[:20]:
        reason = ''
        if p.pk in busy_profile_ids:
            reason = 'Đã tự đăng ký'
        elif p.pk in busy_companion_ids:
            reason = 'Đã được đồng nghiệp đăng ký'
        results.append({
            'id': p.pk,
            'name': p.full_name or p.user.username,
            'department': p.department.name if p.department_id else '',
            'position': p.job_position or '',
            'code': p.employee_code or '',
            'unavailable': bool(reason),
            'reason': reason,
        })
    return JsonResponse(results, safe=False)


@trip_perm_required(*TRIP_MANAGE_ACTIONS)
def manage_list(request):
    search_query = get_search_query(request)
    status = request.GET.get('status') or STATUS_REGISTERED
    qs = TripRegistration.objects.select_related(
        'profile', 'companion1', 'companion2',
    ).prefetch_related('relatives')
    if status != 'all':
        qs = qs.filter(status=status)
    qs = apply_term_search(qs, search_query, ('full_name', 'email', 'phone', 'department_name', 'room_key'))
    page_obj, query_string = paginate_queryset(request, qs)
    return render(request, 'company_trip/manage_list.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'status': status,
        'settings': TripSettings.load(),
        'total': TripRegistration.objects.filter(status=STATUS_REGISTERED).count(),
        'room_colleague': ROOM_COLLEAGUE,
        'room_relative': ROOM_RELATIVE,
        **trip_ui_flags(request.user),
    })


@trip_perm_required('export')
def manage_export(request):
    qs = TripRegistration.objects.filter(status=STATUS_REGISTERED)
    return export_registrations_xlsx(qs)


@require_POST
@trip_perm_required('delete')
def manage_cancel(request, pk):
    reg = get_object_or_404(TripRegistration, pk=pk)
    clear_room_key(reg)
    reg.status = STATUS_CANCELLED
    reg.room_key = ''
    reg.save(update_fields=['status', 'room_key', 'updated_at'])
    if reg.email:
        send_trip_email(
            reg.email,
            reg.full_name,
            reg.gender,
            request=request,
            cancelled=True,
        )
    messages.success(request, f'Đã hủy đăng ký của {reg.full_name}.')
    return redirect('company_trip:manage_list')


def _pending_profiles():
    registered_ids = TripRegistration.objects.filter(
        status=STATUS_REGISTERED,
    ).values_list('profile_id', flat=True)
    return Profile.objects.filter(
        is_employed=True, user__is_active=True,
    ).exclude(pk__in=registered_ids).select_related('user', 'department')


@trip_perm_required('update')
def email_manage(request):
    tpl = TripEmailTemplate.load()
    settings_obj = TripSettings.load()
    settings_form = TripSettingsForm(instance=settings_obj)
    form = TripEmailTemplateForm(instance=tpl)

    if request.method == 'POST':
        action = request.POST.get('action') or 'save_template'
        if action == 'save_settings':
            settings_form = TripSettingsForm(request.POST, instance=settings_obj)
            if settings_form.is_valid():
                settings_form.save()
                messages.success(request, 'Đã lưu cấu hình chuyến đi.')
                return redirect('company_trip:email')
        elif action == 'save_template':
            form = TripEmailTemplateForm(request.POST, instance=tpl)
            if form.is_valid():
                form.save()
                messages.success(request, 'Đã lưu mẫu email.')
                return redirect('company_trip:email')
        elif action == 'bulk_invite':
            sent = 0
            skipped = 0
            for profile in _pending_profiles():
                email = (profile.user.email or '').strip()
                if not email:
                    skipped += 1
                    continue
                if send_trip_email(
                    email,
                    profile.full_name or profile.user.username,
                    profile.gender or '',
                    request=request,
                    phone=domestic_phone(profile.phone),
                    department=profile.department.name if profile.department_id else '',
                ):
                    sent += 1
                else:
                    skipped += 1
            messages.success(request, f'Đã gửi {sent} email mời. Bỏ qua {skipped}.')
            return redirect('company_trip:email')
        elif action == 'resend_registered':
            sent = 0
            skipped = 0
            regs = TripRegistration.objects.filter(
                status=STATUS_REGISTERED,
            ).select_related('companion1', 'companion1__user')
            for reg in regs:
                if not (reg.email or '').strip():
                    skipped += 1
                    continue
                extra = {
                    'room_type': reg.bed_type or reg.room_type or '',
                    'companions': _companion_names_for(reg, recipient='owner'),
                    'phone': reg.phone or '',
                    'department': reg.department_name or '',
                }
                if (reg.pickup_point or '').strip():
                    extra['pickup'] = reg.pickup_point
                if send_trip_email(
                    reg.email,
                    reg.full_name,
                    reg.gender,
                    request=request,
                    **extra,
                ):
                    sent += 1
                else:
                    skipped += 1
            messages.success(request, f'Đã gửi lại {sent} thư theo mẫu đang lưu. Bỏ qua {skipped}.')
            return redirect('company_trip:email')

    pending = _pending_profiles()
    preview_subject, preview_html = render_trip_message(
        'Nguyễn Văn A',
        'M',
        request=request,
        room_type='Phòng giường đôi (double)',
        companions='Trần Văn B',
        phone='0901234567',
        department='Hành chính',
    )
    return render(request, 'company_trip/email.html', {
        'form': form,
        'settings_form': settings_form,
        'settings': settings_obj,
        'pending_count': pending.count(),
        'preview_subject': preview_subject,
        'preview_html': preview_html,
    })
