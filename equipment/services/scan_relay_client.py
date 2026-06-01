"""Gọi scan_relay_server trên máy Windows IT (Tailscale)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .scan_backend import relay_http_url, relay_secret, relay_timeout


class ScanRelayError(RuntimeError):
    pass


def _post(path: str, payload: dict) -> dict:
    url = f'{relay_http_url()}{path}'
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'X-Relay-Secret': relay_secret(),
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=relay_timeout()) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        try:
            data = json.loads(detail)
            message = data.get('message', detail)
        except json.JSONDecodeError:
            message = detail[:500]
        raise ScanRelayError(f'Relay HTTP {exc.code}: {message}') from exc
    except urllib.error.URLError as exc:
        raise ScanRelayError(
            f'Không kết nối relay quét ({relay_http_url()}). '
            f'Máy IT bật scan_relay_server.py và Tailscale chưa? ({exc.reason})'
        ) from exc


def scan_targets_remote(*, targets: list[dict], scan_user: str, scan_pass: str) -> dict:
    return _post('/scan/targets', {
        'scan_user': scan_user,
        'scan_pass': scan_pass,
        'targets': targets,
    })


def scan_range_remote(*, start_ip: str, end_ip: str, scan_user: str, scan_pass: str) -> dict:
    return _post('/scan/range', {
        'scan_user': scan_user,
        'scan_pass': scan_pass,
        'start_ip': start_ip,
        'end_ip': end_ip,
    })
