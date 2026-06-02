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
        cfg_get,
        load_config,
        load_state,
        normalize_urls,
        poll_rescan,
        post_report,
        save_state,
        user_fields_from_config,
    )
    import time

    force_once = '--once' in sys.argv

    def run_once() -> int:
        cfg = load_config()
        report_url, poll_url, secret = normalize_urls(cfg)
        if not secret or not report_url:
            print('Thieu [portal] secret / url trong justplay_agent.ini', file=sys.stderr)
            return 1

        info = collect_info()
        if not info:
            print('Khong doc duoc serial BIOS.', file=sys.stderr)
            return 1

        state = load_state()
        rescan_at = poll_rescan(poll_url=poll_url, api_secret=secret, serial=info['serial'])
        server_rescan = rescan_at or ''
        last_acked = state.get('last_acked_rescan', '')
        force = force_once or (server_rescan and server_rescan != last_acked)
        interval = int(cfg_get(cfg, 'agent', 'interval_minutes', '30') or '30')
        last_report = state.get('last_report_ts', 0)
        due = (time.time() - last_report) >= interval * 60

        if not force and not due and state.get('boot_reported'):
            return 0

        user_fields = user_fields_from_config(cfg)
        ok = post_report(
            report_url=report_url,
            api_secret=secret,
            info=info,
            user_fields=user_fields,
        )
        if ok:
            state['last_report_ts'] = time.time()
            state['boot_reported'] = True
            if server_rescan:
                state['last_acked_rescan'] = server_rescan
            save_state(state)
            print(f"OK: {info.get('hostname')} -> portal")
            return 0
        print('Gui portal that bai.', file=sys.stderr)
        return 2

    if '--once' in sys.argv:
        return run_once()

    run_once()
    cfg = load_config()
    poll_sec = max(15, int(cfg_get(cfg, 'agent', 'poll_seconds', '60') or '60'))
    try:
        while True:
            time.sleep(poll_sec)
            run_once()
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
