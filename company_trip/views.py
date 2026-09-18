import json
import random

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from company_trip.constants import STATUS_CANCELLED, STATUS_REGISTERED
from company_trip.decorators import company_trip_admin_required
from company_trip.email_service import send_trip_email
from company_trip.excel_export import export_registrations_xlsx
from company_trip.forms import (
    TripEmailTemplateForm,
    TripRegistrationForm,
    TripSettingsForm,
)
from company_trip.models import SpinNumber, TripEmailTemplate, TripRegistration, TripSettings
from company_trip.rooms import apply_companions_on_register, assign_room_group, clear_room_key, generate_room_key
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


def _snapshot_from_profile(profile) -> dict:
    return {
        'full_name': profile.full_name or profile.user.get_full_name() or profile.user.username,
        'email': profile.user.email or '',
        'phone': profile.phone or '',
        'gender': profile.gender or '',
        'department_name': profile.department.name if profile.department_id else '',
        'date_of_birth': profile.date_of_birth,
    }


@company_trip_admin_required
def hub(request):
    return redirect('company_trip:manage_list')


@company_trip_admin_required
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
        })

    if not ok:
        return render(request, 'company_trip/closed.html', {
            'reason': reason,
            'settings': settings_obj,
        })

    if request.method == 'POST':
        form = TripRegistrationForm(request.POST, current_profile=profile)
        if form.is_valid():
            snap = _snapshot_from_profile(profile)
            reg = existing or TripRegistration(profile=profile, user=request.user)
            for k, v in snap.items():
                setattr(reg, k, v)
            phone = form.cleaned_data.get('phone') or snap['phone']
            reg.phone = phone
            reg.room_type = form.cleaned_data['room_type']
            reg.vegetarian = form.cleaned_data['vegetarian']
            reg.allergy_note = form.cleaned_data.get('allergy_note') or ''
            reg.pickup_point = form.cleaned_data.get('pickup_point') or ''
            reg.breakfast_choice = form.cleaned_data['breakfast_choice']
            reg.route = form.cleaned_data.get('route') or ''
            reg.detail_route = form.cleaned_data.get('detail_route') or ''
            reg.shopping = form.cleaned_data['shopping']
            reg.note = form.cleaned_data.get('note') or ''
            reg.companion1 = form.cleaned_data.get('companion1_obj')
            reg.companion2 = form.cleaned_data.get('companion2_obj')
            reg.organized_committee = form.cleaned_data.get('organized_committee', False)
            reg.status = STATUS_REGISTERED
            reg.save()
            apply_companions_on_register(reg)

            if reg.email:
                send_trip_email(
                    reg.email,
                    reg.full_name,
                    reg.gender,
                    request=request,
                    room_type=reg.room_type,
                    route=reg.route,
                )
            messages.success(request, 'Đăng ký Company Trip thành công.')
            return redirect('company_trip:thank_you')
    else:
        initial = {
            'phone': profile.phone or '',
            'room_type': existing.room_type if existing else None,
        }
        form = TripRegistrationForm(initial=initial, current_profile=profile)

    return render(request, 'company_trip/register.html', {
        'form': form,
        'settings': settings_obj,
        'profile': profile,
        'snapshot': _snapshot_from_profile(profile),
    })


@company_trip_admin_required
def thank_you(request):
    profile = get_profile(request.user)
    reg = TripRegistration.objects.filter(profile=profile, status=STATUS_REGISTERED).first() if profile else None
    return render(request, 'company_trip/thank_you.html', {
        'already_submitted': False,
        'settings': TripSettings.load(),
        'registration': reg,
    })


@require_GET
@company_trip_admin_required
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
    results = []
    for p in qs.order_by('full_name')[:20]:
        results.append({
            'id': p.pk,
            'name': p.full_name or p.user.username,
            'department': p.department.name if p.department_id else '',
            'position': p.job_position or '',
            'code': p.employee_code or '',
        })
    return JsonResponse(results, safe=False)


@company_trip_admin_required
def manage_list(request):
    search_query = get_search_query(request)
    status = request.GET.get('status') or STATUS_REGISTERED
    qs = TripRegistration.objects.select_related('profile', 'companion1', 'companion2')
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
    })


@company_trip_admin_required
def manage_export(request):
    qs = TripRegistration.objects.filter(status=STATUS_REGISTERED)
    return export_registrations_xlsx(qs)


@require_POST
@company_trip_admin_required
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


@company_trip_admin_required
def rooms_manage(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        reg = get_object_or_404(TripRegistration, pk=request.POST.get('registration_id'))
        if action == 'clear':
            clear_room_key(reg)
            messages.success(request, 'Đã xóa mã phòng.')
        elif action == 'assign':
            key = (request.POST.get('room_key') or '').strip() or generate_room_key()
            companion_ids = [
                int(x) for x in (request.POST.get('companion_ids') or '').split(',')
                if x.strip().isdigit()
            ]
            companions = list(TripRegistration.objects.filter(
                profile_id__in=companion_ids, status=STATUS_REGISTERED,
            ))
            assign_room_group(reg, companions, key)
            messages.success(request, f'Đã gán mã phòng {key}.')
        return redirect('company_trip:rooms')

    search_query = get_search_query(request)
    qs = TripRegistration.objects.filter(status=STATUS_REGISTERED).select_related('profile')
    qs = apply_term_search(qs, search_query, ('full_name', 'room_key', 'department_name'))
    page_obj, query_string = paginate_queryset(request, qs)

    groups = {}
    for r in TripRegistration.objects.filter(status=STATUS_REGISTERED).exclude(room_key=''):
        groups.setdefault(r.room_key, []).append(r.full_name)

    return render(request, 'company_trip/rooms.html', {
        'page_obj': page_obj,
        'query_string': query_string,
        'search_query': search_query,
        'groups': groups,
        'settings': TripSettings.load(),
    })


@company_trip_admin_required
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
            registered_ids = TripRegistration.objects.filter(
                status=STATUS_REGISTERED,
            ).values_list('profile_id', flat=True)
            targets = Profile.objects.filter(
                is_employed=True, user__is_active=True,
            ).exclude(pk__in=registered_ids).select_related('user')
            sent = 0
            skipped = 0
            for p in targets:
                email = (p.user.email or '').strip()
                if not email:
                    skipped += 1
                    continue
                if send_trip_email(
                    email,
                    p.full_name or p.user.username,
                    p.gender or '',
                    request=request,
                ):
                    sent += 1
                else:
                    skipped += 1
            messages.success(request, f'Đã gửi {sent} email mời. Bỏ qua {skipped}.')
            return redirect('company_trip:email')

    pending = Profile.objects.filter(
        is_employed=True, user__is_active=True,
    ).exclude(
        pk__in=TripRegistration.objects.filter(status=STATUS_REGISTERED).values_list('profile_id', flat=True)
    ).count()

    return render(request, 'company_trip/email.html', {
        'form': form,
        'settings_form': settings_form,
        'settings': settings_obj,
        'pending_count': pending,
    })


def _ensure_spin_pool():
    if SpinNumber.objects.count() == 0:
        SpinNumber.objects.bulk_create([SpinNumber(number=i) for i in range(1000)])


@company_trip_admin_required
def spin_page(request):
    _ensure_spin_pool()
    return render(request, 'company_trip/spin.html', {
        'settings': TripSettings.load(),
        'remaining': SpinNumber.objects.filter(shown=False).count(),
        'total': SpinNumber.objects.count(),
    })


@company_trip_admin_required
def check_lucky(request):
    """Giống luckyspin gốc: ưu tiên số lucky chưa quay; không đánh dấu số thường."""
    _ensure_spin_pool()
    lucky_item = SpinNumber.objects.filter(shown=False, lucky=True).order_by('number').first()
    if lucky_item:
        lucky_item.shown = True
        lucky_item.save(update_fields=['shown'])
        return JsonResponse({
            'has_lucky': True,
            'number': f'{lucky_item.number:03d}',
        })
    random_item = SpinNumber.objects.filter(shown=False).order_by('?').first()
    if random_item:
        return JsonResponse({
            'has_lucky': False,
            'number': f'{random_item.number:03d}',
        })
    return JsonResponse({
        'has_lucky': False,
        'number': None,
        'message': 'Đã quay hết tất cả các số.',
    })


@company_trip_admin_required
def spin_api(request):
    """Giống luckyspin gốc: ưu tiên lucky chưa show, rồi random; hết thì reset shown."""
    _ensure_spin_pool()
    lucky_numbers = SpinNumber.objects.filter(lucky=True, shown=False).order_by('number')
    if lucky_numbers.exists():
        chosen = lucky_numbers.first()
    else:
        available = list(SpinNumber.objects.filter(shown=False))
        if not available:
            SpinNumber.objects.all().update(shown=False)
            available = list(SpinNumber.objects.filter(shown=False))
        chosen = random.choice(available)
    chosen.shown = True
    chosen.save(update_fields=['shown'])
    return JsonResponse({
        'ok': True,
        'result': f'{chosen.number:03d}',
        'lucky': chosen.lucky,
        'remaining': SpinNumber.objects.filter(shown=False).count(),
    })


@require_POST
@company_trip_admin_required
def spin_seed(request):
    if SpinNumber.objects.count() == 0:
        SpinNumber.objects.bulk_create([SpinNumber(number=i) for i in range(1000)])
    try:
        data = json.loads(request.body.decode() or '{}')
    except json.JSONDecodeError:
        data = {}
    lucky_nums = data.get('lucky_numbers') or []
    if lucky_nums:
        SpinNumber.objects.filter(number__in=lucky_nums).update(lucky=True)
    return JsonResponse({'ok': True, 'total': SpinNumber.objects.count()})
