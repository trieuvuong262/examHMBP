"""Gửi magic packet Wake-on-LAN (UDP broadcast) hoặc qua relay NAS trong LAN."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request

from django.conf import settings

_MAC_RE = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')


def normalize_mac(raw: str) -> str:
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', raw or '')
    if len(cleaned) != 12:
        raise ValueError('Địa chỉ MAC không hợp lệ')
    mac = ':'.join(cleaned[i:i + 2] for i in range(0, 12, 2)).upper()
    if not _MAC_RE.match(mac):
        raise ValueError('Địa chỉ MAC không hợp lệ')
    return mac


def broadcast_address_for(ip: str | None) -> str:
    configured = (getattr(settings, 'RUSTDESK_WOL_BROADCAST', '') or '').strip()
    if configured:
        return configured
    if ip:
        parts = str(ip).strip().split('.')
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return '.'.join(parts[:3] + ['255'])
    return '255.255.255.255'


def build_magic_packet(mac: str) -> bytes:
    mac_bytes = bytes.fromhex(normalize_mac(mac).replace(':', ''))
    return b'\xff' * 6 + mac_bytes * 16


def send_wake_on_lan(
    mac: str,
    *,
    ip_address: str | None = None,
    broadcast: str | None = None,
    port: int | None = None,
) -> str:
    """Gửi magic packet. Trả về địa chỉ broadcast đã dùng."""
    packet = build_magic_packet(mac)
    target = broadcast or broadcast_address_for(ip_address)
    wol_port = port if port is not None else int(getattr(settings, 'RUSTDESK_WOL_PORT', 9))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (target, wol_port))
    finally:
        sock.close()
    return target


def _relay_secret() -> str:
    secret = (getattr(settings, 'RUSTDESK_WOL_RELAY_SECRET', '') or '').strip()
    if secret:
        return secret
    return (getattr(settings, 'RUSTDESK_ENROLL_SECRET', '') or '').strip()


def send_wake_via_relay(
    mac: str,
    *,
    ip_address: str | None = None,
    broadcast: str | None = None,
) -> str:
    """Gọi HTTP relay trên NAS (cùng LAN / Tailscale) để gửi magic packet."""
    url = (getattr(settings, 'RUSTDESK_WOL_RELAY_URL', '') or '').strip()
    if not url:
        raise ValueError('Chưa cấu hình RUSTDESK_WOL_RELAY_URL')
    secret = _relay_secret()
    if not secret:
        raise ValueError('Chưa cấu hình RUSTDESK_WOL_RELAY_SECRET')

    payload = {
        'secret': secret,
        'mac_address': normalize_mac(mac),
    }
    target_broadcast = broadcast or broadcast_address_for(ip_address)
    if target_broadcast:
        payload['broadcast'] = target_broadcast

    body = json.dumps(payload).encode('utf-8')
    timeout = float(getattr(settings, 'RUSTDESK_WOL_RELAY_TIMEOUT', 5))
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json; charset=utf-8',
            'User-Agent': 'JustPlay-Portal-WoL/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
            data = json.loads(raw or '{}')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')[:300]
        raise OSError(f'Relay NAS trả HTTP {exc.code}: {detail}') from exc
    except urllib.error.URLError as exc:
        raise OSError(f'Không kết nối được relay NAS: {exc.reason}') from exc
    except json.JSONDecodeError as exc:
        raise OSError('Relay NAS trả JSON không hợp lệ') from exc

    if data.get('status') != 'ok':
        raise OSError(data.get('message') or 'Relay NAS từ chối yêu cầu WoL')

    return str(data.get('broadcast') or target_broadcast or '')


def dispatch_wake_on_lan(
    mac: str,
    *,
    ip_address: str | None = None,
    broadcast: str | None = None,
) -> tuple[str, str]:
    """Gửi WoL — relay NAS nếu có URL, không thì từ máy chạy Portal. Trả về (broadcast, mode)."""
    relay_url = (getattr(settings, 'RUSTDESK_WOL_RELAY_URL', '') or '').strip()
    if relay_url:
        target = send_wake_via_relay(mac, ip_address=ip_address, broadcast=broadcast)
        return target, 'relay'
    target = send_wake_on_lan(mac, ip_address=ip_address, broadcast=broadcast)
    return target, 'direct'
