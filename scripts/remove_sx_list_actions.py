"""Remove actions column cells from SX list templates (row click opens detail)."""
import re
from pathlib import Path

KEEP = {"work_assignment_list.html", "costing_cost_type_list.html"}
root = Path(__file__).resolve().parents[1] / "san_xuat" / "templates" / "san_xuat"
pat = re.compile(
    r'\s*<td class="npl-col[^"]*" data-col="actions">.*?</td>',
    re.DOTALL,
)

for f in sorted(root.glob("*_list.html")):
    if f.name in KEEP:
        continue
    text = f.read_text(encoding="utf-8")
    new = pat.sub("", text)
    if new != text:
        f.write_text(new, encoding="utf-8")
        print("removed actions:", f.name)
