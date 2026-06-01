#!/usr/bin/env python3
"""
HTTP relay quét WMI — chạy trên máy Windows IT (LAN + Tailscale).

Portal VPS gọi relay khi user bấm Quét trên web.

  python scan_relay_server.py

Cấu hình: scan_relay.env (EQUIPMENT_RELAY_SECRET, EQUIPMENT_RELAY_BIND)
"""

from __future__ import annotations

import json
import os
import platform
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from equipment.relay.wmi_standalone import (  # noqa: E402
    detect_lan_ip_range,
    parse_ip_range,
    probe_ip,
    scan_ip_list,
    scan_target_entry,
)


def load_env() -> None:
    env_path = ROOT / 'scan_relay.env'
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_path, override=True)
    except ImportError:
        for line in env_path.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip())


load_env()

RELAY_SECRET = os.getenv('EQUIPMENT_RELAY_SECRET', '') or os.getenv('EQUIPMENT_AGENT_SECRET', '')
BIND_HOST = os.getenv('EQUIPMENT_RELAY_BIND', '0.0.0.0')
BIND_PORT = int(os.getenv('EQUIPMENT_RELAY_PORT', '8765'))


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class RelayHandler(BaseHTTPRequestHandler):
    server_version = 'JustPlayScanRelay/1.0'

    def log_message(self, format: str, *args) -> None:
        sys.stderr.write('%s - %s\n' % (self.address_string(), format % args))

    def _read_json(self) -> dict | None:
        length = int(self.headers.get('Content-Length', 0))
        if length <= 0:
            return None
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except json.JSONDecodeError:
            return None

    def _check_auth(self) -> bool:
        if not RELAY_SECRET:
            return False
        header = self.headers.get('X-Relay-Secret', '')
        return header == RELAY_SECRET

    def do_GET(self) -> None:
        if urlparse(self.path).path == '/health':
            _json_response(self, 200, {'status': 'ok', 'platform': platform.system()})
            return
        _json_response(self, 404, {'status': 'error', 'message': 'Not found'})

    def do_POST(self) -> None:
        if platform.system().lower() != 'windows':
            _json_response(self, 503, {'status': 'error', 'message': 'Relay chỉ chạy trên Windows.'})
            return
        if not self._check_auth():
            _json_response(self, 403, {'status': 'error', 'message': 'Sai relay secret.'})
            return

        path = urlparse(self.path).path
        data = self._read_json()
        if not data:
            _json_response(self, 400, {'status': 'error', 'message': 'JSON không hợp lệ.'})
            return

        scan_user = (data.get('scan_user') or '').strip()
        scan_pass = data.get('scan_pass') or ''
        if not scan_user or not scan_pass:
            _json_response(self, 400, {'status': 'error', 'message': 'Thiếu scan_user / scan_pass.'})
            return

        if path == '/scan/targets':
            self._handle_targets(data, scan_user, scan_pass)
        elif path == '/scan/range':
            self._handle_range(data, scan_user, scan_pass)
        elif path == '/scan/lan':
            self._handle_lan(data, scan_user, scan_pass)
        else:
            _json_response(self, 404, {'status': 'error', 'message': 'Not found'})

    def _handle_targets(self, data: dict, scan_user: str, scan_pass: str) -> None:
        targets = data.get('targets') or []
        results = []
        count_ip = 0
        count_wmi = 0
        for item in targets:
            entry = scan_target_entry(
                target_id=str(item.get('id') or ''),
                hostname=item.get('hostname') or None,
                ip_address=item.get('ip_address') or None,
                username=scan_user,
                password=scan_pass,
            )
            if entry.get('ip_updated'):
                count_ip += 1
            if entry.get('wmi_updated'):
                count_wmi += 1
            results.append(entry)
        _json_response(self, 200, {
            'status': 'ok',
            'results': results,
            'summary': {'ip': count_ip, 'wmi': count_wmi, 'total': len(results)},
        })

    def _handle_range(self, data: dict, scan_user: str, scan_pass: str) -> None:
        start_ip = (data.get('start_ip') or '').strip()
        end_ip = (data.get('end_ip') or '').strip()
        try:
            ips = parse_ip_range(start_ip, end_ip)
        except ValueError as exc:
            _json_response(self, 400, {'status': 'error', 'message': str(exc)})
            return

        probes = []
        for ip in ips:
            probe = probe_ip(ip, username=scan_user, password=scan_pass)
            if probe:
                probes.append(probe)

        _json_response(self, 200, {
            'status': 'ok',
            'found': len(probes),
            'probes': probes,
            'start_ip': start_ip,
            'end_ip': end_ip,
        })

    def _handle_lan(self, data: dict, scan_user: str, scan_pass: str) -> None:
        try:
            start_ip, end_ip, label = detect_lan_ip_range()
        except ValueError as exc:
            _json_response(self, 400, {'status': 'error', 'message': str(exc)})
            return
        try:
            ips = parse_ip_range(start_ip, end_ip)
        except ValueError as exc:
            _json_response(self, 400, {'status': 'error', 'message': str(exc)})
            return
        probes = scan_ip_list(ips, username=scan_user, password=scan_pass)
        _json_response(self, 200, {
            'status': 'ok',
            'found': len(probes),
            'probes': probes,
            'start_ip': start_ip,
            'end_ip': end_ip,
            'lan_label': label,
        })


def main() -> int:
    if platform.system().lower() != 'windows':
        print('scan_relay_server.py chỉ chạy trên Windows.', file=sys.stderr)
        return 1
    if not RELAY_SECRET:
        print('Thiếu EQUIPMENT_RELAY_SECRET trong scan_relay.env', file=sys.stderr)
        return 1

    server = ThreadingHTTPServer((BIND_HOST, BIND_PORT), RelayHandler)
    print(f'JustPlay scan relay listening on http://{BIND_HOST}:{BIND_PORT}')
    print('Health: GET /health  |  Scan: POST /scan/targets, /scan/range')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
