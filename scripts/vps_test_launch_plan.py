"""Smoke test Kế hoạch ra mắt sản phẩm trên VPS.

Chạy trong container web:
    docker compose exec -T web python scripts/vps_test_launch_plan.py

Test chỉ đọc dữ liệu và render các URL, không tạo/sửa/xóa dữ liệu.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Cho phép chạy trực tiếp từ thư mục scripts hoặc qua manage.py.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import Client
from django.template.loader import get_template

from ra_mat_sp.models import (
    GROUP_WEIGHTS,
    LaunchPlan,
    LaunchPlanGroupOwner,
    Status,
    TaskGroup,
)
from ra_mat_sp.services import go_conditions, readiness

OK = 0
FAIL = 0


def check(name: str, condition: bool) -> None:
    global OK, FAIL
    if condition:
        OK += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name}")


# Import/compile template checks.
for name in (
    "ra_mat_sp/dashboard.html",
    "ra_mat_sp/plan_list.html",
    "ra_mat_sp/plan_detail.html",
    "ra_mat_sp/plan_form.html",
    "ra_mat_sp/calendar.html",
    "ra_mat_sp/my_tasks.html",
    "ra_mat_sp/settings.html",
):
    try:
        get_template(name)
        check(f"template {name}", True)
    except Exception as exc:
        check(f"template {name}: {exc}", False)

check("readiness weights total 100", sum(GROUP_WEIGHTS.values()) == 100)
check("all required statuses present", set(Status.values) >= {
    "draft", "plan_pending", "preparing", "at_risk", "launch_pending",
    "ready", "launched", "reviewing", "done", "paused", "cancelled",
})
check("task groups include required groups", set(TaskGroup.values) >= {
    "product", "production", "price", "marketing", "channel", "logistics",
})

plans = list(LaunchPlan.objects.order_by("-updated_at")[:20])
check("launch plan queryset", plans is not None)
for plan in plans:
    try:
        result = readiness(plan)
        check(f"readiness plan {plan.code}", 0 <= result["pct"] <= 100)
        rows = go_conditions(plan)
        check(f"go gates plan {plan.code}", bool(rows))
        if plan.status in {Status.DRAFT, Status.PLAN_PENDING, Status.PREPARING, Status.AT_RISK}:
            check(
                f"group owners plan {plan.code}",
                LaunchPlanGroupOwner.objects.filter(plan=plan).count() >= len(TaskGroup.values),
            )
    except Exception as exc:
        check(f"plan {plan.code}: {exc}", False)

User = get_user_model()
user = User.objects.filter(is_active=True).order_by("-is_superuser", "id").first()
check("active user exists", user is not None)
if user:
    client = Client(HTTP_HOST="portal.justplay.vn", secure=True)
    client.force_login(user)
    paths = (
        "/ke-hoach-ra-mat/",
        "/ke-hoach-ra-mat/ke-hoach/",
        "/ke-hoach-ra-mat/lich/?view=year",
        "/ke-hoach-ra-mat/viec-cua-toi/",
        "/ke-hoach-ra-mat/cho-duyet/",
        "/ke-hoach-ra-mat/thiet-lap/",
    )
    for path in paths:
        response = client.get(path, follow=True)
        check(f"GET {path} -> {response.status_code}", response.status_code < 500)
        if response.status_code >= 500:
            print(response.content.decode("utf-8", errors="replace")[:2000])

print("---")
print(f"Results: {OK} passed, {FAIL} failed")
if FAIL:
    raise SystemExit(1)
