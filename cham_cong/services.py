import time
from datetime import timedelta

from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from audit.utils import _iter_forwarded_ips, get_client_device_info
from cham_cong.calc import (
    attendance_work_date,
    build_span,
    classify_day,
    distance_m,
    in_reminder_window,
    ip_matches_rule,
    place_time,
)
from cham_cong.models import (
    AttendanceDay,
    AttendanceLog,
    AttendancePolicy,
    Holiday,
    ShiftAssignment,
    TimesheetPeriod,
    WorkSite,
    WorkSiteIp,
)
from hrm.permissions import get_profile


def candidate_ips(request) -> list[str]:
    found = []
    info = get_client_device_info(request)
    for key in ('public_ip', 'local_ip', 'client_ip'):
        value = (info.get(key) or '').strip()
        if value:
            found.append(value)
    found.extend(_iter_forwarded_ips(request))
    unique = []
    seen = set()
    for ip in found:
        if ip and ip not in seen:
            seen.add(ip)
            unique.append(ip)
    return unique


def detected_ip_label(request) -> str:
    info = get_client_device_info(request)
    parts = []
    if info.get('public_ip'):
        parts.append(f"IP công cộng {info['public_ip']}")
    if info.get('local_ip'):
        parts.append(f"IP nội bộ {info['local_ip']}")
    if not parts and info.get('client_ip'):
        parts.append(info['client_ip'])
    return ' · '.join(parts) or 'Chưa nhận được IP'


def _cached(user, name, producer):
    """Nhớ trong request hiện tại. Cùng một người không hỏi lại ca và popup."""
    flag = f'_cc_{name}_set'
    if getattr(user, flag, False):
        return getattr(user, name)
    value = producer()
    setattr(user, flag, True)
    setattr(user, name, value)
    return value


def resolve_shift(user):
    return _cached(user, 'shift', lambda: _resolve_shift(user))


def _resolve_shift(user):
    profile = get_profile(user)
    if not profile or not profile.is_employed:
        return None
    base = ShiftAssignment.objects.filter(is_active=True, shift__is_active=True).select_related('shift')
    own = base.filter(user=user).first()
    if own:
        return own.shift
    if profile.division_id:
        by_division = base.filter(division_id=profile.division_id, user__isnull=True).first()
        if by_division:
            return by_division.shift
    if profile.department_id:
        by_department = base.filter(
            department_id=profile.department_id,
            division__isnull=True,
            user__isnull=True,
        ).first()
        if by_department:
            return by_department.shift
    return None


_policy_cache = {'at': 0.0, 'obj': None}
_sites_cache = {'at': 0.0, 'rows': None}
_badge_cache = {}
_POLICY_TTL = 60
_SITES_TTL = 30
_BADGE_TTL = 20


def cached_policy():
    now = time.monotonic()
    obj = _policy_cache['obj']
    if obj is not None and now - _policy_cache['at'] < _POLICY_TTL:
        return obj
    obj = AttendancePolicy.load()
    _policy_cache['at'] = now
    _policy_cache['obj'] = obj
    return obj


def clear_policy_cache():
    _policy_cache['at'] = 0.0
    _policy_cache['obj'] = None


def is_holiday(day) -> bool:
    return Holiday.objects.filter(holiday_date=day).exists()


def span_for(shift, work_date, policy=None):
    policy = policy or cached_policy()
    return build_span(shift, work_date, is_holiday=is_holiday(work_date), policy=policy)


def active_sites():
    now = time.monotonic()
    rows = _sites_cache['rows']
    if rows is not None and now - _sites_cache['at'] < _SITES_TTL:
        return rows
    rows = list(WorkSite.objects.filter(is_active=True).prefetch_related('ips'))
    _sites_cache['at'] = now
    _sites_cache['rows'] = rows
    return rows


def clear_sites_cache():
    _sites_cache['at'] = 0.0
    _sites_cache['rows'] = None


def verify_location(request, latitude=None, longitude=None):
    """IP WiFi khớp trước. Không khớp thì GPS phải nằm trong bán kính một địa điểm."""
    sites = active_sites()
    if not sites:
        return None, 'Nhân sự chưa khai báo địa điểm chấm công.'

    ips = candidate_ips(request)
    ip_hits = []
    for site in sites:
        for rule in site.ips.all():
            if any(ip_matches_rule(ip, rule.cidr) for ip in ips):
                ip_hits.append((site, rule.cidr))
                break
    if ip_hits:
        site, matched = ip_hits[0]
        matched_ip = next((ip for ip in ips if ip_matches_rule(ip, matched)), matched)
        return {
            'site': site,
            'method': AttendanceDay.METHOD_IP,
            'ip': matched_ip,
            'distance_m': None,
            'latitude': None,
            'longitude': None,
        }, None

    if latitude is None or longitude is None or latitude == '' or longitude == '':
        return None, 'Máy không dùng WiFi công ty. Bật định vị của trình duyệt rồi chấm lại.'

    try:
        lat = float(latitude)
        lng = float(longitude)
    except (TypeError, ValueError):
        return None, 'Tọa độ định vị không hợp lệ.'

    nearest = None
    nearest_distance = None
    for site in sites:
        meters = distance_m(lat, lng, site.latitude, site.longitude)
        if nearest_distance is None or meters < nearest_distance:
            nearest = site
            nearest_distance = meters
        if meters <= site.radius_m:
            return {
                'site': site,
                'method': AttendanceDay.METHOD_GPS,
                'ip': ips[0] if ips else '',
                'distance_m': int(meters),
                'latitude': lat,
                'longitude': lng,
            }, None
    place = nearest.name if nearest else 'công ty'
    return None, f'Ngoài bán kính {place}. Chấm công bị chặn.'


def open_attendance(user, when=None):
    if when is None:
        return _cached(user, 'open_day', lambda: _open_attendance(user, None))
    return _open_attendance(user, when)


def _open_attendance(user, when=None):
    when = when or timezone.now()
    local = timezone.localtime(when)
    return (
        AttendanceDay.objects.filter(
            user=user,
            clock_in__isnull=False,
            clock_out__isnull=True,
            work_date__gte=local.date() - timedelta(days=1),
        )
        .select_related('shift', 'site')
        .order_by('-work_date')
        .first()
    )


def month_is_locked(day) -> bool:
    return TimesheetPeriod.objects.filter(
        year=day.year, month=day.month, is_locked=True,
    ).exists()


def current_work_date(user, when=None):
    when = when or timezone.now()
    open_day = open_attendance(user, when)
    if open_day:
        return open_day.work_date
    shift = resolve_shift(user)
    if shift:
        return attendance_work_date(shift, when)
    return timezone.localtime(when).date()


def should_force_punch(user, when=None) -> bool:
    if when is not None:
        return _should_force_punch(user, when)
    return _cached(user, 'force_punch', lambda: _should_force_punch(user, None))


def _should_force_punch(user, when=None) -> bool:
    from cham_cong.permissions import can_punch

    profile = get_profile(user)
    if not profile or not profile.is_employed or not can_punch(user):
        return False
    shift = resolve_shift(user)
    if not shift:
        return False
    when = when or timezone.now()
    local = timezone.localtime(when)
    policy = cached_policy()
    # Ngoài khung giờ thì chủ nhật, ngày lễ và tháng khóa cũng không nhắc.
    cheap = build_span(shift, local.date(), is_holiday=False, policy=policy)
    if not in_reminder_window(cheap, when, policy.reminder_lead_minutes):
        return False
    if is_holiday(local.date()) or month_is_locked(local.date()):
        return False
    return not AttendanceDay.objects.filter(
        user=user, work_date=local.date(), clock_in__isnull=False,
    ).exists()


def apply_classification(day: AttendanceDay, shift, policy=None):
    policy = policy or cached_policy()
    span = span_for(shift, day.work_date, policy) if shift else None
    metrics = classify_day(day.clock_in, day.clock_out, day.break_out, day.break_in, span)
    for key, value in metrics.items():
        setattr(day, key, value)
    day.shift = shift
    return day


def stamp_event_time(work_date, clock_time, shift):
    if not shift:
        return place_time(work_date, clock_time, clock_time, False)
    return place_time(work_date, clock_time, shift.start_time, shift.crosses_midnight)


def write_log(actor, action, message, target=None):
    AttendanceLog.objects.create(
        actor=actor,
        target_user=target,
        action=action,
        message=message[:255],
    )


def team_user_ids(manager):
    return _cached(manager, 'team_ids', lambda: _team_user_ids(manager))


def _team_user_ids(manager):
    profile = get_profile(manager)
    if not profile:
        return []
    ids = set(profile.subordinates.filter(is_active=True).values_list('pk', flat=True))
    for slot in profile.concurrent_positions.filter(is_active=True):
        ids.update(slot.subordinates.filter(is_active=True).values_list('pk', flat=True))
    ids.discard(manager.pk)
    return list(ids)


def pending_badge_counts(user) -> tuple[int, int, int, int]:
    """Số đơn chờ. Giữ 20 giây để 500 người mở portal không đếm lại liên tục."""
    from cham_cong.models import AttendanceAdjustment, AttendanceSupplement, LeaveRequest, PayAdjustment
    from cham_cong.permissions import can_view_company

    now = time.monotonic()
    hit = _badge_cache.get(user.pk)
    if hit and now - hit[0] < _BADGE_TTL:
        return hit[1]
    if can_view_company(user):
        counts = (
            AttendanceSupplement.objects.filter(status=AttendanceSupplement.STATUS_PENDING).count(),
            AttendanceAdjustment.objects.filter(status=AttendanceAdjustment.STATUS_PENDING).count(),
            LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING).count(),
            PayAdjustment.objects.filter(status=PayAdjustment.STATUS_PENDING).count(),
        )
    else:
        ids = team_user_ids(user)
        if not ids:
            counts = (0, 0, 0, 0)
        else:
            counts = (
                AttendanceSupplement.objects.filter(status=AttendanceSupplement.STATUS_PENDING, user_id__in=ids).count(),
                AttendanceAdjustment.objects.filter(status=AttendanceAdjustment.STATUS_PENDING, user_id__in=ids).count(),
                LeaveRequest.objects.filter(status=LeaveRequest.STATUS_PENDING, user_id__in=ids).count(),
                PayAdjustment.objects.filter(status=PayAdjustment.STATUS_PENDING, user_id__in=ids).count(),
            )
    if len(_badge_cache) > 2000:
        _badge_cache.clear()
    _badge_cache[user.pk] = (now, counts)
    return counts


@receiver(post_save, sender=AttendancePolicy)
@receiver(post_delete, sender=AttendancePolicy)
def _policy_changed(sender, **kwargs):
    clear_policy_cache()


@receiver(post_save, sender=WorkSite)
@receiver(post_delete, sender=WorkSite)
@receiver(post_save, sender=WorkSiteIp)
@receiver(post_delete, sender=WorkSiteIp)
def _sites_changed(sender, **kwargs):
    clear_sites_cache()


def visible_attendance(user):
    from cham_cong.permissions import can_view_company

    if can_view_company(user):
        return AttendanceDay.objects.all()
    ids = team_user_ids(user)
    return AttendanceDay.objects.filter(Q(user=user) | Q(user_id__in=ids))
