"""PC dùng chung: máy đã có agent — user mới chỉ xác nhận trên portal."""
from __future__ import annotations

from equipment.models import Device, UserAgentRegistration


def device_has_agent(device: Device) -> bool:
    """Thiết bị đã có ít nhất một lần đăng ký agent."""
    if not device or not device.serial_number:
        return False
    return UserAgentRegistration.objects.filter(
        serial_number=device.serial_number,
    ).exists()


def find_device_for_client_request(request) -> Device | None:
    """
    Nhận diện PC từ cookie trình duyệt (client-device.js / hoàn tất cài agent).
    Chỉ trả về thiết bị đã có agent đăng ký.
    """
    serial_cookie = (request.COOKIES.get('jp_agent_serial') or '').strip()
    hostname = (request.COOKIES.get('jp_hostname') or '').strip()
    ip = (request.COOKIES.get('jp_local_ip') or '').strip()

    if serial_cookie:
        device = Device.objects.filter(serial_number=serial_cookie).first()
        if device and device_has_agent(device):
            return device

    base_qs = Device.objects.filter(
        agent_registrations__isnull=False,
    ).distinct()

    if hostname:
        device = base_qs.filter(hostname__iexact=hostname).first()
        if device:
            return device

    if ip:
        device = base_qs.filter(ip_address=ip).first()
        if device:
            return device

    return None


def user_registered_on_device(user, device: Device) -> bool:
    if not user or not device or not device.serial_number:
        return False
    if device.assigned_user_id == user.pk:
        return True
    return UserAgentRegistration.objects.filter(
        user=user,
        serial_number=device.serial_number,
    ).exists()


def get_registered_users(device: Device):
    """Danh sách user đã đăng ký trên thiết bị (assigned + registrations)."""
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user_ids = set()
    if device.assigned_user_id:
        user_ids.add(device.assigned_user_id)
    reg_ids = UserAgentRegistration.objects.filter(
        serial_number=device.serial_number,
    ).values_list('user_id', flat=True)
    user_ids.update(reg_ids)
    return User.objects.filter(pk__in=user_ids).order_by('username')


def confirm_user_on_shared_device(user, device: Device) -> Device:
    """
    Gắn user vào thiết bị đã có agent — không ghi đè assigned_user nếu đã có người khác.
    """
    from equipment.services.agent_device import apply_user_profile_to_device

    UserAgentRegistration.objects.update_or_create(
        user=user,
        serial_number=device.serial_number,
        defaults={'device': device},
    )

    if not device.assigned_user_id:
        fields = apply_user_profile_to_device(device, user)
        fields.append('updated_at')
        device.save(update_fields=sorted(set(fields)))
    return device


def get_shared_pc_context_for_gate(request, user):
    """
    Context cho trang gate: PC đã có agent, user chưa đăng ký → có thể xác nhận dùng chung.
    """
    device = find_device_for_client_request(request)
    if not device or not device_has_agent(device):
        return None
    if user_registered_on_device(user, device):
        return None

    registered_users = list(get_registered_users(device))
    return {
        'device': device,
        'registered_users': registered_users,
        'can_confirm_shared': True,
    }
