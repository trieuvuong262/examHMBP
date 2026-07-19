import json
from pathlib import Path
from urllib.parse import unquote

HIST = Path(r"C:\Users\Vuong-IT\AppData\Roaming\Cursor\User\History")

TARGETS = [
    "/san_xuat/urls.py",
    "/san_xuat/views_hub.py",
    "/san_xuat/hub_models.py",
    "/kho_npl/models.py",
]

results = {t: [] for t in TARGETS}

for entries_path in HIST.glob("*/entries.json"):
    try:
        data = json.loads(entries_path.read_text(encoding="utf-8"))
    except Exception:
        continue
    res = unquote(data.get("resource", "")).replace("\\", "/")
    for t in TARGETS:
        if res.endswith(t):
            folder = entries_path.parent
            ents = data.get("entries") or []
            for ent in ents:
                fp = folder / ent["id"]
                if fp.exists():
                    size = fp.stat().st_size
                    results[t].append((ent.get("timestamp"), size, fp))

for t in TARGETS:
    print("====", t, "matches:", len(results[t]))
    for ts, size, fp in sorted(results[t], key=lambda x: x[1], reverse=True)[:8]:
        print(f"  size={size:7d} ts={ts} path={fp}")
