#!/bin/bash
set -euo pipefail
cd /opt/portaljustplay
docker compose exec -T web python manage.py shell <<'PYEOF'
import json, subprocess
from audit.services.nas_monitor import _dsm_request, NasMonitorError, _rclone_about
from nas_storage.nas_paths import default_nas_rclone_remote

paths = ["/backup", "/10_HE_THONG_CNTT", "/01_BAN_GIAM_DOC"]
try:
    data = _dsm_request(
        "SYNO.FileStation.List", "getinfo", version=2,
        params={"path": json.dumps(paths), "additional": '["size"]'},
        timeout=20,
    )
    print("getinfo:", json.dumps(data, indent=2)[:2000])
except NasMonitorError as e:
    print("getinfo err", e)

remote = default_nas_rclone_remote()
for name in ["backup", "10_HE_THONG_CNTT"]:
    p = f"{remote}{name}" if remote.endswith(":") else f"{remote.rstrip('/')}/{name}"
    print("about", name, _rclone_about(p, timeout=15))
    proc = subprocess.run(["rclone", "size", p, "--json"], capture_output=True, text=True, timeout=120)
    print("size", name, "rc=", proc.returncode, proc.stdout[:500], proc.stderr[:200])
PYEOF
