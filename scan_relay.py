#!/usr/bin/env python3
"""
Quét WMI tập trung trên máy Windows IT (Cách 1) — đẩy kết quả lên Portal VPS.

Chạy trên 1 máy Windows trong LAN công ty (không cài trên từng PC user).
Cấu hình: copy scan_relay.env.example → scan_relay.env

  python scan_relay.py
  python scan_relay.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from equipment.relay.wmi_standalone import parse_ip_range, probe_ip  # noqa: E402


def load_config(env_path: Path | None = None) -> dict[str, str]:
    path = env_path or ROOT / 'scan_relay.env'
    if path.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(path, override=True)
        except ImportError:
            for line in path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                os.environ.setdefault(key.strip(), value.strip())

    cfg = {
        'portal_url': (os.getenv('EQUIPMENT_RELAY_URL') or os.getenv('PORTAL_PUBLIC_BASE_URL') or '').rstrip('/'),
        'api_secret': os.getenv('EQUIPMENT_AGENT_SECRET', ''),
        'start_ip': os.getenv('SCAN_START_IP', ''),
        'end_ip': os.getenv('SCAN_END_IP', ''),
        'scan_user': os.getenv('SCAN_USER', ''),
        'scan_pass': os.getenv('SCAN_PASS', ''),
        'max_hosts': os.getenv('SCAN_MAX_HOSTS', '255'),
    }
    return cfg


def validate_config(cfg: dict[str, str]) -> list[str]:
    errors = []
    if platform.system().lower() != 'windows':
        errors.append('scan_relay.py chỉ chạy trên Windows.')
    if not cfg['api_secret']:
        errors.append('Thiếu EQUIPMENT_AGENT_SECRET (trong scan_relay.env).')
    if not cfg['start_ip'] or not cfg['end_ip']:
        errors.append('Thiếu SCAN_START_IP / SCAN_END_IP.')
    if not cfg['scan_user'] or not cfg['scan_pass']:
        errors.append('Thiếu SCAN_USER / SCAN_PASS (tài khoản domain admin quét WMI).')
    if not cfg['portal_url']:
        errors.append('Thiếu EQUIPMENT_RELAY_URL hoặc PORTAL_PUBLIC_BASE_URL.')
    return errors


def api_endpoint(portal_url: str) -> str:
    base = portal_url.rstrip('/')
    if base.endswith('/thiet-bi/api/agent-report'):
        return base
    if base.endswith('/thiet-bi'):
        return f'{base}/api/agent-report/'
    return f'{base}/thiet-bi/api/agent-report/'


def post_report(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode('utf-8'))


def run_scan(*, dry_run: bool = False, env_path: Path | None = None) -> int:
    cfg = load_config(env_path)
    errors = validate_config(cfg)
    if errors:
        for msg in errors:
            print(f'Lỗi cấu hình: {msg}', file=sys.stderr)
        return 1

    try:
        max_hosts = int(cfg['max_hosts'])
    except ValueError:
        max_hosts = 255

    try:
        ips = parse_ip_range(cfg['start_ip'], cfg['end_ip'], max_hosts=max_hosts)
    except ValueError as exc:
        print(f'Lỗi dải IP: {exc}', file=sys.stderr)
        return 1

    endpoint = api_endpoint(cfg['portal_url'])
    username = cfg['scan_user']
    password = cfg['scan_pass']
    secret = cfg['api_secret']

    print(f'Quét {len(ips)} IP ({cfg["start_ip"]} – {cfg["end_ip"]})')
    print(f'Portal: {endpoint}')
    if dry_run:
        print('(dry-run — không gửi lên portal)')

    found = 0
    created = 0
    updated = 0
    failed = 0

    for ip in ips:
        payload = probe_ip(ip, username=username, password=password)
        if not payload:
            continue
        found += 1
        hostname = payload.get('hostname') or ip
        print(f'  + {ip}  {hostname}  serial={payload["serial"]}')

        if dry_run:
            continue

        body = {**payload, 'api_secret': secret}
        try:
            result = post_report(endpoint, body)
            if result.get('status') == 'success':
                if result.get('created'):
                    created += 1
                else:
                    updated += 1
            else:
                failed += 1
                print(f'    ! API: {result.get("message", result)}', file=sys.stderr)
        except urllib.error.HTTPError as exc:
            failed += 1
            detail = exc.read().decode('utf-8', errors='replace')
            print(f'    ! HTTP {exc.code}: {detail[:200]}', file=sys.stderr)
        except urllib.error.URLError as exc:
            failed += 1
            print(f'    ! Kết nối: {exc.reason}', file=sys.stderr)

    print(
        f'Hoàn tất: tìm thấy {found} máy.'
        + (f' Tạo mới {created}, cập nhật {updated}, lỗi {failed}.' if not dry_run else ' (dry-run)')
    )
    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description='Quét WMI LAN → Portal JustPlay (máy IT tập trung)')
    parser.add_argument('--dry-run', action='store_true', help='Chỉ quét, không POST lên portal')
    parser.add_argument('--env', type=Path, default=None, help='Đường dẫn file scan_relay.env')
    args = parser.parse_args()
    return run_scan(dry_run=args.dry_run, env_path=args.env)


if __name__ == '__main__':
    raise SystemExit(main())
