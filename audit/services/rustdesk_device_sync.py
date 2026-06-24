"""Liên kết RustDeskHost với thiết bị IT và đồng bộ MAC / IP."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Q

from audit.models import RustDeskHost


@dataclass
class RustDeskDeviceSyncResult:
    linked: int = 0
    mac_updated: int = 0
    skipped: int = 0
    missing_mac: int = 0

    @property
    def changed(self) -> int:
        return self.linked + self.mac_updated


def find_device_for_host(host: RustDeskHost):
    """Tìm thiết bị IT khớp hostname hoặc IP (ưu tiên hostname)."""
    from equipment.models import Device
    from equipment.scope import filter_devices_for_scope, SCOPE_IT

    if host.device_id:
        device = Device.objects.filter(pk=host.device_id).first()
        if device:
            return device

    base_qs = filter_devices_for_scope(Device.objects.all(), SCOPE_IT)
    hostname = (host.hostname or '').strip()
    if hostname:
        match = base_qs.filter(hostname__iexact=hostname).order_by('-updated_at').first()
        if match:
            return match

    if host.ip_address:
        match = base_qs.filter(ip_address=host.ip_address).order_by('-updated_at').first()
        if match:
            return match

    return None


def apply_device_to_host(host: RustDeskHost, device, *, overwrite_mac: bool = False) -> tuple[bool, bool, bool]:
    """Gắn thiết bị và copy MAC. Trả về (linked_changed, mac_changed, meta_changed)."""
    from equipment.services.device_mac import resolve_device_mac

    linked_changed = False
    mac_changed = False
    meta_changed = False

    if host.device_id != device.pk:
        host.device = device
        linked_changed = True

    device_mac = resolve_device_mac(device)
    if device_mac and (overwrite_mac or not (host.mac_address or '').strip()):
        if host.mac_address != device_mac:
            host.mac_address = device_mac
            mac_changed = True

    if device_mac and not (device.mac_address or '').strip():
        device.mac_address = device_mac
        device.save(update_fields=['mac_address', 'updated_at'])

    if not host.hostname and device.hostname:
        host.hostname = device.hostname[:128]
        meta_changed = True
    if not host.ip_address and device.ip_address:
        host.ip_address = device.ip_address
        meta_changed = True

    return linked_changed, mac_changed, meta_changed


def sync_host_from_device(
    host: RustDeskHost,
    *,
    save: bool = True,
    overwrite_mac: bool = False,
) -> tuple[bool, bool]:
    """Đồng bộ một máy RustDesk từ thiết bị IT. Trả về (linked_changed, mac_changed)."""
    device = find_device_for_host(host)
    if not device:
        return False, False

    linked_changed, mac_changed, meta_changed = apply_device_to_host(
        host,
        device,
        overwrite_mac=overwrite_mac,
    )
    if save and (linked_changed or mac_changed or meta_changed):
        update_fields = ['updated_at']
        if linked_changed:
            update_fields.append('device')
        if mac_changed:
            update_fields.append('mac_address')
        if meta_changed:
            if host.hostname:
                update_fields.append('hostname')
            if host.ip_address:
                update_fields.append('ip_address')
        host.save(update_fields=list(dict.fromkeys(update_fields)))
    return linked_changed, mac_changed


def sync_all_rustdesk_hosts_from_devices(*, overwrite_mac: bool = False) -> RustDeskDeviceSyncResult:
    """Đồng bộ toàn bộ máy RustDesk — liên kết thiết bị + lấy MAC."""
    result = RustDeskDeviceSyncResult()
    hosts = RustDeskHost.objects.select_related('device').order_by('pk')
    for host in hosts:
        device = find_device_for_host(host)
        if not device:
            result.skipped += 1
            continue
        from equipment.services.device_mac import resolve_device_mac

        if not resolve_device_mac(device):
            result.missing_mac += 1
        linked_changed, mac_changed, meta_changed = apply_device_to_host(
            host,
            device,
            overwrite_mac=overwrite_mac,
        )
        if linked_changed or mac_changed or meta_changed:
            update_fields = ['updated_at']
            if linked_changed:
                update_fields.append('device')
                result.linked += 1
            if mac_changed:
                update_fields.append('mac_address')
                result.mac_updated += 1
            if meta_changed:
                if host.hostname:
                    update_fields.append('hostname')
                if host.ip_address:
                    update_fields.append('ip_address')
            host.save(update_fields=list(dict.fromkeys(update_fields)))
        else:
            result.skipped += 1
    return result


def hosts_missing_mac_qs():
    """Máy RustDesk chưa có MAC (kể cả từ thiết bị liên kết)."""
    return RustDeskHost.objects.filter(
        Q(mac_address='') | Q(mac_address__isnull=True),
    ).filter(
        Q(device__isnull=True) | Q(device__mac_address='') | Q(device__mac_address__isnull=True),
    )
