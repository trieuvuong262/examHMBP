#!/usr/bin/env python3
"""
JustPlay — WoL Relay (chạy trên NAS luôn bật trong LAN)

Portal gọi HTTP → NAS gửi magic packet UDP trong mạng nội bộ.

Cài trên Synology / Linux:
  1. Copy file này lên NAS (vd. /volume1/scripts/JustPlay-WoL-Relay.py)
  2. Chọn secret mạnh, trùng với Portal .env:
       export WOL_RELAY_SECRET='your-long-secret'
  3. Chạy thử:
       python3 JustPlay-WoL-Relay.py
  4. Task Scheduler (Synology) → chạy lúc khởi động:
       python3 /volume1/scripts/JustPlay-WoL-Relay.py

Portal (.env trên VPS):
  RUSTDESK_WOL_RELAY_URL=http://<IP-NAS>:39280/wake
  RUSTDESK_WOL_RELAY_SECRET=your-long-secret

IP NAS: dùng IP LAN (192.168.x.x) chỉ khi VPS cùng mạng/VPN.
Nếu VPS ở internet: cài Tailscale trên NAS + VPS, dùng IP 100.x.x.x của NAS.

Kiểm tra từ máy khác:
  curl -sS -X POST http://<NAS>:39280/wake \\
    -H 'Content-Type: application/json' \\
    -d '{"secret":"your-long-secret","mac_address":"AA:BB:CC:DD:EE:FF"}'
"""

from __future__ import annotations

import json
import os
import re
import socket
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_MAC_RE = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')
_DEFAULT_PORT = 39280


def normalize_mac(raw: str) -> str:
    cleaned = re.sub(r'[^0-9A-Fa-f]', '', raw or '')
    if len(cleaned) != 12:
        raise ValueError('Địa chỉ MAC không hợp lệ')
    mac = ':'.join(cleaned[i:i + 2] for i in range(0, 12, 2)).upper()
    if not _MAC_RE.match(mac):
        raise ValueError('Địa chỉ MAC không hợp lệ')
    return mac


def broadcast_address_for(ip: str | None, configured: str = '') -> str:
    if configured:
        return configured
    if ip:
        parts = str(ip).strip().split('.')
        if len(parts) == 4 and all(part.isdigit() and 0 <= int(part) <= 255 for part in parts):
            return '.'.join(parts[:3] + ['255'])
    default = (os.environ.get('WOL_RELAY_BROADCAST') or '').strip()
    if default:
        return default
    return '255.255.255.255'


def send_magic_packet(mac: str, broadcast: str, port: int = 9) -> None:
    mac_bytes = bytes.fromhex(normalize_mac(mac).replace(':', ''))
    packet = b'\xff' * 6 + mac_bytes * 16
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
    finally:
        sock.close()


def make_handler(*, secret: str, default_broadcast: str, wol_port: int):
    class WoLRelayHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            sys.stderr.write('[WoL-Relay] ' + (fmt % args) + '\n')

        def _json(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ('/', '/health'):
                self._json(200, {'status': 'ok', 'service': 'justplay-wol-relay'})
                return
            self._json(404, {'status': 'error', 'message': 'Not found'})

        def do_POST(self):
            if self.path not in ('/wake', '/'):
                self._json(404, {'status': 'error', 'message': 'Not found'})
                return
            length = int(self.headers.get('Content-Length') or 0)
            raw = self.rfile.read(length) if length else b'{}'
            try:
                data = json.loads(raw.decode('utf-8') or '{}')
            except json.JSONDecodeError:
                self._json(400, {'status': 'error', 'message': 'JSON không hợp lệ'})
                return

            if (data.get('secret') or '') != secret:
                self._json(403, {'status': 'error', 'message': 'Sai secret'})
                return

            try:
                mac = normalize_mac(data.get('mac_address') or data.get('mac') or '')
            except ValueError as exc:
                self._json(400, {'status': 'error', 'message': str(exc)})
                return

            broadcast = (data.get('broadcast') or '').strip() or broadcast_address_for(
                data.get('ip_address') or data.get('ip'),
                default_broadcast,
            )
            try:
                send_magic_packet(mac, broadcast, wol_port)
            except OSError as exc:
                self._json(500, {'status': 'error', 'message': str(exc)})
                return

            self._json(200, {
                'status': 'ok',
                'message': f'Đã gửi WoL tới {mac} ({broadcast})',
                'broadcast': broadcast,
                'mac_address': mac,
            })

    return WoLRelayHandler


def main() -> int:
    secret = (os.environ.get('WOL_RELAY_SECRET') or '').strip()
    if not secret:
        print('Thiếu WOL_RELAY_SECRET', file=sys.stderr)
        return 1

    bind = (os.environ.get('WOL_RELAY_BIND') or '0.0.0.0').strip()
    port = int(os.environ.get('WOL_RELAY_PORT') or _DEFAULT_PORT)
    default_broadcast = (os.environ.get('WOL_RELAY_BROADCAST') or '').strip()
    wol_port = int(os.environ.get('WOL_RELAY_PORT_UDP') or '9')

    handler = make_handler(
        secret=secret,
        default_broadcast=default_broadcast,
        wol_port=wol_port,
    )
    server = ThreadingHTTPServer((bind, port), handler)
    print(f'JustPlay WoL Relay listening on {bind}:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Stopped.', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
