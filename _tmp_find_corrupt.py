from pathlib import Path
import re

root = Path(r"d:\Project\PortalJustPlay\san_xuat\templates")
bad = []
for p in root.rglob("*.html"):
    raw = p.read_bytes()
    if b"\x00TAG" not in raw:
        continue
    t = raw.decode("utf-8", errors="replace")
    bad.append(p)
    print("---", p.relative_to(root))
    for m in re.finditer(r".{0,50}\x00TAG\d+\x00.{0,50}", t):
        print(" ", repr(m.group(0)[:120]))
print("TOTAL", len(bad))
