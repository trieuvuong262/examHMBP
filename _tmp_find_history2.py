import json
from pathlib import Path
from urllib.parse import unquote

HIST = Path(r"C:\Users\Vuong-IT\AppData\Roaming\Cursor\User\History")

TARGETS = [
    "/san_xuat/urls.py",
    "/san_xuat/views_hub.py",
    "/san_xuat/hub_models.py",
    "/kho_npl/models.py",
    "/san_xuat/views_ops.py",
]

for entries_path in HIST.glob("*/entries.json"):
    try:
        data = json.loads(entries_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    res = unquote(data.get("resource", "")).replace("\\", "/")
    for t in TARGETS:
        if res.endswith(t):
            print("FILE:", res)
            print("  folder:", entries_path.parent)
            ents = data.get("entries") or []
            for ent in ents:
                fp = entries_path.parent / ent["id"]
                exists = fp.exists()
                size = fp.stat().st_size if exists else -1
                print(f"    id={ent['id']} ts={ent.get('timestamp')} exists={exists} size={size}")
