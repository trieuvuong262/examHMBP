"""Smoke test: render tất cả màn list SX (200, không lỗi template)."""
from __future__ import annotations

import re
import sys
import traceback

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

LIST_URLS = [
    "san_xuat:overview",
    "san_xuat:plan_overall",
    "san_xuat:plan_detail",
    "san_xuat:plan_npl",
    "san_xuat:npl_purchase_request",
    "san_xuat:purchase_order",
    "san_xuat:dispatch_mo",
    "san_xuat:dispatch_disassembly",
    "san_xuat:dispatch_material_issue_req",
    "san_xuat:dispatch_prod_stats",
    "san_xuat:dispatch_fg_receipt_req",
    "san_xuat:dispatch_npl_surplus",
    "san_xuat:dispatch_wip_handover",
    "san_xuat:dispatch_wip_return",
    "san_xuat:qc_request",
    "san_xuat:qc_sheet",
    "san_xuat:qc_alerts",
    "san_xuat:qc_criteria",
    "san_xuat:qc_criteria_group",
    "san_xuat:qc_sampling",
    "san_xuat:qc_standard_set",
    "san_xuat:qc_defect",
    "san_xuat:qc_defect_group",
    "san_xuat:costing_norm",
    "san_xuat:costing_sheet_list",
    "san_xuat:costing_by_order",
    "san_xuat:costing_cost_types",
    "san_xuat:actual_cost_list",
    "san_xuat:work_assignment_list",
    "san_xuat:capacity_list",
    "san_xuat:packing_list",
    "san_xuat:subcontract_list",
    "san_xuat:ncr_list",
    "san_xuat:downtime_list",
    "san_xuat:unified_catalog",
    "san_xuat:team_hr_map",
    "san_xuat:doc_list",
    "san_xuat:bom_list",
    "san_xuat:traceability",
    "san_xuat:piece_rate_report",
]

ERROR_MARKERS = (
    "NoReverseMatch",
    "TemplateSyntaxError",
    "Exception Type:",
    "Traceback (most recent call last)",
)


def main() -> int:
    User = get_user_model()
    user = User.objects.filter(is_superuser=True).first() or User.objects.first()
    if not user:
        print("FAIL: no user in DB")
        return 1

    client = Client(HTTP_HOST="127.0.0.1")
    client.force_login(user)

    ok = 0
    failed: list[str] = []

    for name in LIST_URLS:
        try:
            url = reverse(name)
        except Exception as exc:
            failed.append(f"{name}: reverse failed — {exc}")
            continue
        try:
            resp = client.get(url)
        except Exception:
            failed.append(f"{name} ({url}):\n{traceback.format_exc()}")
            continue

        body = resp.content.decode("utf-8", errors="replace")
        if resp.status_code != 200:
            title = re.search(r"<title>([^<]+)</title>", body)
            failed.append(
                f"{name} ({url}): HTTP {resp.status_code}"
                + (f" — {title.group(1)}" if title else "")
            )
            continue

        for marker in ERROR_MARKERS:
            if marker in body:
                title = re.search(r"<title>([^<]+)</title>", body)
                failed.append(
                    f"{name} ({url}): contains {marker!r}"
                    + (f" — {title.group(1)}" if title else "")
                )
                break
        else:
            ok += 1
            print(f"OK  {name}")

    print(f"\n{ok}/{len(LIST_URLS)} passed")
    if failed:
        print("\nFAILED:")
        for item in failed:
            print(f"  - {item}")
        return 1
    print("All list pages OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
