"""Lấy địa chỉ MAC từ thiết bị IT — cột mac_address hoặc dữ liệu quét cấu hình."""

from __future__ import annotations

import re

_MAC_RE = re.compile(
    r'\b([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})\b',
)
_SKIP_ADAPTER = re.compile(
    r'virtual|vmware|hyper-v|vpn|tap|loopback|bluetooth|wi-?fi|wlan|npcap|vethernet|docker|wsl',
    re.I,
)
_LAN_ADAPTER = re.compile(
    r'^(ethernet|enp\d+s\d+|eth\d+|lan)\b',
    re.I,
)


def _normalize_mac(raw: str) -> str:
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', raw or '')
    if len(cleaned) != 12:
        return ''
    return ':'.join(cleaned[i:i + 2] for i in range(0, 12, 2)).upper()


def _mac_from_text(text: str) -> str:
    match = _MAC_RE.search(text or '')
    if not match:
        return ''
    return _normalize_mac(match.group(1))


def extract_mac_from_description(description: str) -> str:
    for line in (description or '').splitlines():
        if line.strip().lower().startswith('mac chính:'):
            return _mac_from_text(line.split(':', 1)[-1])
    return ''


def extract_lan_mac_from_network_text(network: str) -> str:
    """Ưu tiên Ethernet / enp* — bỏ qua VMware, Wi‑Fi, Bluetooth."""
    if not network:
        return ''

    parts = re.split(r'[,;\n]+', network)
    lan_candidate = ''
    any_candidate = ''
    for part in parts:
        chunk = part.strip()
        if not chunk or '=' not in chunk:
            continue
        name, _, value = chunk.partition('=')
        name = name.strip()
        value = value.strip()
        if not value or value.isdigit():
            continue
        mac = _mac_from_text(value)
        if not mac:
            continue
        if _SKIP_ADAPTER.search(name):
            continue
        any_candidate = any_candidate or mac
        if _LAN_ADAPTER.search(name):
            lan_candidate = mac
    return lan_candidate or any_candidate


def extract_mac_from_configuration(configuration: str) -> str:
    text = configuration or ''
    for line in text.splitlines():
        lower = line.lower()
        if lower.startswith('mạng:') or lower.startswith('card mạng:'):
            return extract_lan_mac_from_network_text(line.split(':', 1)[-1])
    return extract_lan_mac_from_network_text(text)


def resolve_device_mac(device, *, prefer_lan: bool = True) -> str:
    """MAC dùng cho WoL — ưu tiên cột mac_address, rồi Ethernet trong quét, rồi MAC chính."""
    if not device:
        return ''

    stored = (getattr(device, 'mac_address', '') or '').strip()
    if stored:
        return _normalize_mac(stored) or stored

    configuration = getattr(device, 'configuration', '') or ''
    description = getattr(device, 'description', '') or ''

    if prefer_lan:
        mac = extract_mac_from_configuration(configuration)
        if mac:
            return mac
        mac = extract_mac_from_description(description)
        if mac:
            return mac
        return extract_lan_mac_from_network_text(description)

    mac = extract_mac_from_description(description)
    if mac:
        return mac
    return extract_mac_from_configuration(configuration)
