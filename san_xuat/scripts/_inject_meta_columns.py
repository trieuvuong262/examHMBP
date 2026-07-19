"""Inject meta columns before action column in SX list templates."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "templates" / "san_xuat"
HEAD = "            {% include 'san_xuat/includes/sx_list_meta_head.html' %}\n"

FILES: dict[str, str] = {
    "plan_overall_list.html": "plan",
    "plan_detail_list.html": "plan",
    "plan_npl_list.html": "plan",
    "npl_purchase_request_list.html": "req",
    "purchase_order_list.html": "order",
    "costing_sheet_list.html": "sheet",
    "costing_order_list.html": "sheet",
    "costing_cost_type_list.html": "ct",
    "dispatch_mo_list.html": "order",
    "disassembly_list.html": "item",
    "dispatch_material_issue_req_list.html": "req",
    "dispatch_prod_stats_list.html": "stat",
    "dispatch_fg_receipt_req_list.html": "req",
    "npl_surplus_list.html": "item",
    "wip_handover_list.html": "item",
    "wip_return_list.html": "item",
    "qc_request_list.html": "req",
    "qc_sheet_list.html": "inspection",
    "qc_alerts_list.html": "alert",
    "work_assignment_list.html": "item",
    "packing_list.html": "item",
    "subcontract_list.html": "item",
    "ncr_list.html": "c",
    "actual_cost_list.html": "s",
    "downtime_list.html": "e",
    "team_hr_map.html": "m",
    "doc_list.html": "doc",
    "bom_list.html": "bom",
}

ACTION_TH = re.compile(
    r'(<th(?=[^>]*class="[^"]*text-end)[^>]*>\s*</th>|<th>\s*</th>)(\s*</tr>)',
    re.IGNORECASE,
)
ACTION_TD = re.compile(
    r'<td(?: class="text-end")?>\s*(?:<a [^>]*\bbtn\b|<form )',
    re.IGNORECASE,
)
LAST_TD = re.compile(r'<td\b', re.IGNORECASE)


def strip_meta(text: str) -> str:
    return re.sub(
        r"\s*{% include ['\"]san_xuat/includes/sx_list_meta_[^%]+%}\s*",
        "\n",
        text,
    )


def fix_header(text: str) -> str:
    if "sx_list_meta_head" in text:
        return text

    def _repl(match: re.Match[str]) -> str:
        return HEAD + match.group(1) + match.group(2)

    new, n = ACTION_TH.subn(_repl, text, count=1)
    if n:
        return new

    return re.sub(
        r"(<thead[^>]*>\s*<tr[^>]*>.*?)(</tr>)",
        lambda m: m.group(1) + HEAD + m.group(2),
        text,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )


def fix_rows(text: str, obj_var: str) -> str:
    row_snip = (
        f"            {{% include 'san_xuat/includes/sx_list_meta_row.html' with obj={obj_var} %}}\n"
    )

    def _tr_repl(match: re.Match[str]) -> str:
        tr = match.group(0)
        if "colspan" in tr or "sx_list_meta_row" in tr or "{% empty %}" in tr:
            return tr
        if "{{" not in tr:
            return tr
        matches = list(ACTION_TD.finditer(tr))
        if matches:
            pos = matches[-1].start()
        else:
            tds = list(LAST_TD.finditer(tr))
            pos = tds[-1].start() if tds else None
        if pos is None:
            return tr.replace("</tr>", row_snip + "          </tr>", 1)
        return tr[:pos] + row_snip + tr[pos:]

    return re.sub(r"<tr[^>]*>.*?</tr>", _tr_repl, text, flags=re.DOTALL | re.IGNORECASE)


def bump_colspan(text: str) -> str:
    return re.sub(
        r'(<tr[^>]*>.*?colspan=")(\d+)(")',
        lambda m: f'{m.group(1)}{int(m.group(2)) + 2}{m.group(3)}',
        text,
        count=1,
        flags=re.DOTALL | re.IGNORECASE,
    )


def patch_file(path: Path, obj_var: str) -> None:
    text = strip_meta(path.read_text(encoding="utf-8"))
    text = fix_header(text)
    text = fix_rows(text, obj_var)
    if 'colspan="' in text:
        text = bump_colspan(text)
    path.write_text(encoding="utf-8", data=text)


def main() -> None:
    for name, var in FILES.items():
        p = ROOT / name
        if not p.exists():
            print("MISSING", name)
            continue
        patch_file(p, var)
        print("OK", name)


if __name__ == "__main__":
    main()
