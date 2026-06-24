#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json
from audit.services.nas_monitor import (
    NasMonitorError,
    _dsm_request,
    _rclone_about,
    collect_nas_metrics,
    dsm_configured,
)
from nas_storage.nas_paths import default_nas_rclone_remote, rclone_listing_available

print("=== NAS Monitor Diagnostic ===")
print("dsm_configured:", dsm_configured())
m = collect_nas_metrics()
print("error:", m.get("error"))
print("cpu:", json.dumps(m.get("cpu")))
print("ram:", json.dumps(m.get("ram")))
print("disk:", json.dumps(m.get("disk")))
print("--- shares ---")
for row in m.get("shares") or []:
    print(row.get("name"), "|", row.get("display"), "| pct:", row.get("used_percent"), "| used:", row.get("used_bytes"), "| total:", row.get("total_bytes"))
print("--- volumes ---")
for row in m.get("volumes") or []:
    print(row.get("name"), "|", row.get("display"), "| pct:", row.get("used_percent"))
if dsm_configured():
    try:
        data = _dsm_request(
            "SYNO.FileStation.List",
            "list_share",
            version=2,
            params={"additional": '["size","real_path","volume_status"]', "limit": "0"},
            timeout=20,
        )
        print("--- raw list_share (3) ---")
        for sh in (data.get("shares") or [])[:3]:
            print(sh.get("name"), json.dumps(sh.get("additional")))
    except NasMonitorError as exc:
        print("list_share err:", exc)
remote = default_nas_rclone_remote()
print("rclone base:", remote)
if rclone_listing_available():
    import subprocess
    proc = subprocess.run(["rclone", "lsd", remote, "--json"], capture_output=True, text=True, timeout=30)
    if proc.returncode == 0:
        entries = json.loads(proc.stdout)
        for entry in entries[:5]:
            name = entry.get("Name") or entry.get("name")
            path = f"{remote}{name}" if remote.endswith(":") else f"{remote.rstrip('/')}/{name}"
            print("rclone", name, _rclone_about(path, timeout=12))
PYEOF
