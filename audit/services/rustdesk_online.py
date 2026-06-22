"""Hỏi trạng thái online peer qua RustDesk hbbs (OnlineRequest / OnlineResponse)."""

from __future__ import annotations

import socket
import struct
from typing import Iterable

from django.conf import settings
from django.core.cache import cache

CACHE_KEY = 'rustdesk:online:states'


def _cache_ttl_sec() -> int:
    return int(getattr(settings, 'RUSTDESK_ONLINE_CACHE_SEC', 5))


def normalize_rustdesk_id(raw: str) -> str:
    return ''.join(c for c in (raw or '') if c.isdigit())


def _encode_varint(value: int) -> bytes:
    parts: list[int] = []
    n = value
    while n > 0x7F:
        parts.append((n & 0x7F) | 0x80)
        n >>= 7
    parts.append(n)
    return bytes(parts)


def _decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    result = 0
    shift = 0
    while offset < len(data):
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not (byte & 0x80):
            return result, offset
        shift += 7
    raise ValueError('varint decode truncated')


def _encode_length_delimited(field_number: int, payload: bytes) -> bytes:
    tag = (field_number << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(payload)) + payload


def _encode_string_field(field_number: int, value: str) -> bytes:
    encoded = value.encode('utf-8')
    tag = (field_number << 3) | 2
    return _encode_varint(tag) + _encode_varint(len(encoded)) + encoded


def build_online_request_message(*, requester_id: str, peer_ids: Iterable[str]) -> bytes:
    inner = b''.join(
        [
            _encode_string_field(1, requester_id),
            *(_encode_string_field(2, peer_id) for peer_id in peer_ids),
        ]
    )
    return _encode_length_delimited(23, inner)


def _parse_online_response_states(message: bytes) -> bytes | None:
    offset = 0
    while offset < len(message):
        tag, offset = _decode_varint(message, offset)
        field_number = tag >> 3
        wire_type = tag & 7
        if wire_type != 2:
            continue
        length, offset = _decode_varint(message, offset)
        chunk = message[offset:offset + length]
        offset += length
        if field_number != 24:
            continue
        inner_offset = 0
        while inner_offset < len(chunk):
            inner_tag, inner_offset = _decode_varint(chunk, inner_offset)
            inner_field = inner_tag >> 3
            inner_wire = inner_tag & 7
            if inner_wire != 2:
                continue
            inner_len, inner_offset = _decode_varint(chunk, inner_offset)
            payload = chunk[inner_offset:inner_offset + inner_len]
            inner_offset += inner_len
            if inner_field == 1:
                return payload
    return None


def _peer_states_from_bytes(states: bytes, peer_count: int) -> list[bool]:
    result: list[bool] = []
    for i in range(peer_count):
        byte_idx = i // 8
        bit_idx = 7 - (i % 8)
        if byte_idx >= len(states):
            result.append(False)
            continue
        result.append(bool(states[byte_idx] & (1 << bit_idx)))
    return result


def _encode_frame(payload: bytes) -> bytes:
    length = len(payload)
    if length <= 0x3F:
        return bytes([length << 2]) + payload
    if length <= 0x3FFF:
        return struct.pack('<H', (length << 2) | 0x1) + payload
    if length <= 0x3FFFFF:
        header_value = (length << 2) | 0x2
        return struct.pack('<H', header_value & 0xFFFF) + bytes([header_value >> 16]) + payload
    if length <= 0x3FFFFFFF:
        return struct.pack('<I', (length << 2) | 0x3) + payload
    raise ValueError('payload too large')


def _decode_frame_header(first_byte: int, rest: bytes) -> tuple[int, int]:
    head_len = (first_byte & 0x3) + 1
    if head_len == 1:
        payload_len = first_byte >> 2
        return payload_len, head_len
    if len(rest) < head_len - 1:
        raise ValueError('incomplete frame header')
    header = bytes([first_byte]) + rest[:head_len - 1]
    payload_len = header[0]
    if head_len > 1:
        payload_len |= header[1] << 8
    if head_len > 2:
        payload_len |= header[2] << 16
    if head_len > 3:
        payload_len |= header[3] << 24
    payload_len >>= 2
    return payload_len, head_len


def _recv_frame(sock: socket.socket) -> bytes:
    first = _recv_exact(sock, 1)
    if not first:
        return b''
    head_len = (first[0] & 0x3) + 1
    rest = _recv_exact(sock, head_len - 1) if head_len > 1 else b''
    payload_len, _ = _decode_frame_header(first[0], rest)
    if payload_len <= 0 or payload_len > 1_048_576:
        return b''
    return _recv_exact(sock, payload_len)


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining > 0:
        part = sock.recv(remaining)
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    return b''.join(chunks)


def _rendezvous_target() -> tuple[str, int]:
    host_raw = (getattr(settings, 'RUSTDESK_PUBLIC_HOST', '') or 'rd.justplay.vn').strip()
    if ':' in host_raw:
        host, port_text = host_raw.rsplit(':', 1)
        port = int(port_text)
    else:
        host = host_raw
        port = int(getattr(settings, 'RUSTDESK_RENDEZVOUS_PORT', 21116))
    online_port = port - 1
    return host, online_port


def query_peers_online(
    peer_ids: Iterable[str],
    *,
    timeout: float | None = None,
) -> dict[str, bool]:
    """Trả về map {rustdesk_id_digits: is_online}. Lỗi mạng → coi là offline."""
    if not getattr(settings, 'RUSTDESK_ONLINE_CHECK_ENABLED', True):
        return {}

    normalized = [normalize_rustdesk_id(peer_id) for peer_id in peer_ids]
    peer_ids_list = [peer_id for peer_id in normalized if peer_id]
    if not peer_ids_list:
        return {}

    timeout = timeout or float(getattr(settings, 'RUSTDESK_ONLINE_CHECK_TIMEOUT', 3.0))
    host, online_port = _rendezvous_target()
    requester_id = peer_ids_list[0]
    payload = build_online_request_message(requester_id=requester_id, peer_ids=peer_ids_list)
    framed = _encode_frame(payload)

    result = {peer_id: False for peer_id in peer_ids_list}
    try:
        with socket.create_connection((host, online_port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(framed)
            body = _recv_frame(sock)
            if not body:
                return result
            states = _parse_online_response_states(body)
            if states is None:
                return result
            for peer_id, online in zip(peer_ids_list, _peer_states_from_bytes(states, len(peer_ids_list))):
                result[peer_id] = online
    except OSError:
        return result
    return result


def get_peers_online_map(peer_ids: Iterable[str], *, force_refresh: bool = False) -> dict[str, bool]:
    """Cache ngắn để tránh hỏi hbbs mỗi request."""
    peer_ids_list = sorted({normalize_rustdesk_id(peer_id) for peer_id in peer_ids if normalize_rustdesk_id(peer_id)})
    if not peer_ids_list:
        return {}

    cache_token = ','.join(peer_ids_list)
    cache_key = f'{CACHE_KEY}:{hash(cache_token)}'
    if not force_refresh:
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            return cached

    online_map = query_peers_online(peer_ids_list)
    cache.set(cache_key, online_map, _cache_ttl_sec())
    return online_map
