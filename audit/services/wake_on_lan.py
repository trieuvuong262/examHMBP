"""Gửi magic packet Wake-on-LAN (UDP broadcast)."""

from __future__ import annotations

import re
import socket

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
