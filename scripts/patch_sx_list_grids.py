#!/usr/bin/env python3
"""Patch san_xuat list templates — col picker, sortable header, data-col, scripts."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'san_xuat' / 'templates' / 'san_xuat'

PATCHES: dict[str, dict] = {
    'dispatch_mo_list.html': {'cols': ['code', 'product', 'qty', 'order_date', 'due_date', 'status'], 'actions': True},
    'disassembly_list.html': {'cols': ['code', 'product', 'qty', 'mo', 'order_date', 'status'], 'actions': True},
    'dispatch_material_issue_req_list.html': {'cols': ['code', 'mo', 'request_date', 'status', 'issue_doc'], 'actions': True},
    'dispatch_prod_stats_list.html': {'cols': ['code', 'mo', 'stat_date', 'process', 'qty_good', 'qty_defect', 'status'], 'actions': True, 'force_grid': True},
    'dispatch_fg_receipt_req_list.html': {'cols': ['code', 'mo', 'request_date', 'qty', 'status', 'kv_doc'], 'actions': True},
    'npl_surplus_list.html': {'cols': ['code', 'material', 'qty', 'source', 'recorded_at', 'status', 'stock_adj'], 'actions': True},
    'wip_handover_list.html': {'cols': ['code', 'mo', 'from_process', 'to_process', 'qty', 'handover_date', 'status'], 'actions': True},
    'wip_return_list.html': {'cols': ['code', 'mo', 'from_process', 'to_process', 'qty', 'return_date', 'status'], 'actions': True},
    'qc_request_list.html': {'cols': ['code', 'mo', 'product', 'process', 'request_date', 'status'], 'actions': True, 'force_grid': True},
    'qc_sheet_list.html': {'cols': ['code', 'qc_request', 'inspected_at', 'standard', 'qty_sample', 'qty_pass', 'qty_fail', 'result'], 'actions': True, 'force_grid': True},
    'qc_alerts_list.html': {'cols': ['code', 'alert_type', 'mo', 'process', 'qty', 'message', 'status'], 'actions': True},
    'work_assignment_list.html': {'cols': ['code', 'mo', 'title', 'assignee', 'work_task', 'due_date', 'status'], 'actions': True},
    'packing_list.html': {'cols': ['code', 'mo', 'qty', 'lot', 'pack_date', 'status'], 'actions': True},
    'subcontract_list.html': {'cols': ['code', 'vendor', 'product', 'qty', 'order_date', 'status'], 'actions': True},
    'plan_overall_list.html': {'cols': ['code', 'name', 'date_from', 'date_to', 'source', 'line_count', 'status'], 'actions': True},
    'plan_detail_list.html': {'cols': ['code', 'name', 'overall', 'period', 'line_count', 'status'], 'actions': True},
    'plan_npl_list.html': {'cols': ['code', 'name', 'overall', 'line_count', 'status'], 'actions': True},
    'npl_purchase_request_list.html': {'cols': ['code', 'plan', 'request_date', 'due_date', 'line_count', 'status'], 'actions': True},
    'purchase_order_list.html': {'cols': ['code', 'supplier', 'pr', 'total', 'kv_receipt', 'status'], 'actions': True},
    'costing_sheet_list.html': {'cols': ['code', 'name', 'period', 'line_count', 'status'], 'actions': True},
    'costing_order_list.html': {'cols': ['code', 'name', 'kv_order', 'period', 'total', 'status'], 'actions': True},
    'costing_cost_type_list.html': {'cols': ['code', 'name', 'category', 'status'], 'actions': True},
    'ncr_list.html': {'cols': ['code', 'mo', 'disposition', 'qty', 'status'], 'actions': True},
    'actual_cost_list.html': {'cols': ['code', 'mo', 'material', 'labor', 'subcontract', 'total', 'status'], 'actions': True},
    'downtime_list.html': {'cols': ['code', 'event_date', 'reason', 'minutes', 'team', 'mo'], 'meta': False, 'actions': False},
    'team_hr_map.html': {'cols': ['employee_code', 'employee_name', 'team', 'role'], 'meta': False, 'actions': False},
    'bom_list.html': {'cols': ['product_code', 'product_name', 'version', 'status', 'line_count', 'step_count', 'updated_at'], 'actions': True},
    'doc_list.html': {'cols': ['product_code', 'product_name', 'status', 'updated_at'], 'actions': True},
    'costing_bom_list.html': {'cols': ['product_code', 'product_name', 'material', 'labor', 'overhead', 'total', 'sell_price', 'margin'], 'actions': True},
}


def enrich_td_open(tag: str, key: str) -> str:
    if 'data-col=' in tag:
        return tag
    body = tag[3:-1].strip()
    classes = []
    m = re.search(r'class="([^"]*)"', body)
    if m:
        classes = [c for c in m.group(1).split() if c]
        body = re.sub(r'\s*class="[^"]*"', '', body)
    if 'npl-col' not in classes:
        classes.insert(0, 'npl-col')
    attrs = f'class="{" ".join(classes)}" data-col="{key}"'
    if body:
        attrs += f' {body}'
    return f'<td {attrs}>'


def patch_data_row(row: str, col_keys: list[str], *, actions: bool) -> str:
    tags = list(re.finditer(r'<td(\s[^>]*)?>', row))
    if not tags:
        return row
    out = []
    last = 0
    key_i = 0
    for m in tags:
        if key_i >= len(col_keys):
            break
        out.append(row[last:m.start()])
        out.append(enrich_td_open(m.group(0), col_keys[key_i]))
        last = m.end()
        key_i += 1
    out.append(row[last:])
    patched = ''.join(out)
    if actions and 'data-col="actions"' not in patched:
        patched = re.sub(
            r'(<td)(\s[^>]*)(>\s*(?:<a\b|{%))',
            r'\1 class="npl-col text-end" data-col="actions"\3',
            patched,
            count=1,
        )
    return patched


def patch_file(name: str, spec: dict) -> bool:
    path = ROOT / name
    text = path.read_text(encoding='utf-8')
    orig = text

    if "sx_list_col_picker.html" not in text:
        text = text.replace('    </nav>\n', "      {% include 'san_xuat/includes/sx_list_col_picker.html' %}\n    </nav>\n", 1)

    text = re.sub(
        r'<thead class="table-light">\s*<tr>.*?</tr>\s*</thead>',
        '<thead class="table-light">\n          <tr>\n            {% include \'san_xuat/includes/sx_list_grid_head.html\' %}\n          </tr>\n        </thead>',
        text,
        count=1,
        flags=re.DOTALL,
    )

    if 'id="{{ sx_list_table_id }}"' not in text:
        if 'jp-npl-mat-grid-wrap' in text:
            text = re.sub(
                r'(<div class="jp-npl-mat-grid-wrap">\s*<table class=")([^"]*)(")',
                lambda m: (
                    f'{m.group(1)}{m.group(2)}{" jp-npl-mat-grid" if "jp-npl-mat-grid" not in m.group(2) else ""}'
                    f'{m.group(3)} id="{{{{ sx_list_table_id }}}}"'
                ),
                text,
                count=1,
            )
        elif spec.get('force_grid'):
            text = re.sub(
                r'(<table class=")(table table-hover[^"]*)(")',
                r'\1\2 jp-npl-mat-grid\3 id="{{ sx_list_table_id }}"',
                text,
                count=1,
            )

    loop = re.search(r'{% for \w+ in \w+ %}\s*<tr[^>]*>(.*?)</tr>', text, re.DOTALL)
    if loop:
        row_inner = loop.group(1)
        new_inner = patch_data_row(row_inner, spec['cols'], actions=spec.get('actions', False))
        text = text.replace(row_inner, new_inner, 1)

    if 'sx_list_grid_scripts.html' not in text:
        text = text.replace('\n{% endblock %}\n', "\n{% include 'san_xuat/includes/sx_list_grid_scripts.html' %}\n{% endblock %}\n", 1)

    if text != orig:
        path.write_text(text, encoding='utf-8')
        print(f'Patched {name}')
        return True
    print(f'No change {name}')
    return False


if __name__ == '__main__':
    n = sum(patch_file(k, v) for k, v in PATCHES.items())
    print(f'Done: {n}')
