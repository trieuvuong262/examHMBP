#!/usr/bin/env python3
"""Entry point — build: scripts\\build-justplay-agent.cmd"""
from __future__ import annotations

import platform
import sys


def main() -> int:
    if platform.system() != 'Windows':
        print('JustPlay Agent chi chay tren Windows.', file=sys.stderr)
        return 1

    from equipment.agent.core import (
        collect_info,
        load_config,
        normalize_urls,
        post_report,
        user_fields_from_config,
    )

    cfg = load_config()
    report_url, _poll_url, secret = normalize_urls(cfg)
    if not secret or not report_url:
        print('Thieu [portal] secret / url trong justplay_agent.ini', file=sys.stderr)
        return 1

    info = collect_info()
    if not info:
        print('Khong doc duoc serial BIOS.', file=sys.stderr)
        return 1

    user_fields = user_fields_from_config(cfg)
    ok = post_report(
        report_url=report_url,
        api_secret=secret,
        info=info,
        user_fields=user_fields,
    )
    if ok:
        # Bản .exe (PyInstaller) chạy nền — không in ra console khi đăng nhập Windows.
        if not getattr(sys, 'frozen', False):
            print(f"OK: {info.get('hostname')} -> portal")
        return 0
    print('Gui portal that bai.', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
