"""Tạo demo KHSX (KHTT + KHCT + KHNVL) hiển thị trên UI. Chạy trong container web:

    python manage.py shell < san_xuat/scripts/seed_khsx_demo_once.py
hoặc:
    python /tmp/seed_khsx_demo_once.py
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__" and "DJANGO_SETTINGS_MODULE" not in os.environ:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
    import django

    django.setup()

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import (
    SxDetailPlan,
    SxMaterialPlan,
    SxOverallPlan,
    SxOverallPlanLine,
)
from san_xuat.models import ProductTechDoc
from san_xuat.services.planning import (
    add_overall_plan_line,
    confirm_detail_plan,
    confirm_overall_plan,
    create_overall_plan,
    explode_detail_plan_from_overall,
    explode_material_plan,
)

NOTE = "[VPS-DEMO KHSX]"
OVERALL_CODE = "KHTT-2026-KHSX-DEMO"
DETAIL_CODE = "KHCT-2026-KHSX-DEMO"


def main() -> None:
    today = timezone.localdate()
    date_from = today - timedelta(days=today.weekday())  # thứ 2 tuần này
    date_to = date_from + timedelta(days=13)  # 2 tuần

    codes = list(
        ProductTechDoc.objects.filter(is_active=True)
        .order_by("-id")
        .values_list("product_code", flat=True)[:4]
    )
    if not codes:
        # fallback mã phổ biến trên portal
        codes = ["SP008073", "SP008074", "SP008075"]

    user = (
        get_user_model().objects.filter(username="admin").first()
        or get_user_model().objects.filter(is_superuser=True).first()
    )

    with transaction.atomic():
        # Xóa bản demo cũ cùng mã (nếu có) để chạy lại sạch
        SxDetailPlan.objects.filter(code=DETAIL_CODE).delete()
        SxMaterialPlan.objects.filter(overall_plan__code=OVERALL_CODE).delete()
        SxOverallPlan.objects.filter(code=OVERALL_CODE).delete()

        overall = create_overall_plan(
            name="Kế hoạch SX demo (2 tuần)",
            date_from=date_from,
            date_to=date_to,
            code=OVERALL_CODE,
            notes=NOTE,
            user=user,
        )
        overall.is_demo = False
        overall.save(update_fields=["is_demo"])

        for idx, code in enumerate(codes):
            add_overall_plan_line(
                plan_id=overall.pk,
                product_code=code,
                qty_planned=Decimal("400") + idx * 80,
                qty_required=Decimal("450") + idx * 80,
                capacity_per_day=Decimal("80"),
            )

        overall = confirm_overall_plan(plan_id=overall.pk)

        detail = explode_detail_plan_from_overall(
            overall_plan_id=overall.pk,
            code=DETAIL_CODE,
            name="KH chi tiết demo từ KHTT",
        )
        detail.is_demo = False
        detail.notes = NOTE
        detail.save(update_fields=["is_demo", "notes"])
        detail = confirm_detail_plan(plan_id=detail.pk, allow_over_capacity=True)

        mat = None
        try:
            mat = explode_material_plan(
                overall_plan_id=overall.pk,
                code="KHNVL-2026-KHSX-DEMO",
                name="KHNVL demo từ KHTT",
            )
            mat.is_demo = False
            mat.notes = NOTE
            mat.status = SxOverallPlan.STATUS_CONFIRMED
            mat.save(update_fields=["is_demo", "notes", "status"])
        except Exception as exc:  # noqa: BLE001 — BOM có thể thiếu
            mat = None
            print(f"KHNVL bỏ qua: {exc}")

    print("OK demo KHSX")
    print(f"  KHTT: {overall.code} · {overall.status} · {overall.date_from}→{overall.date_to}")
    print(f"  dòng SP: {SxOverallPlanLine.objects.filter(plan=overall).count()} · {', '.join(codes)}")
    print(f"  KHCT: {detail.code} · {detail.status} · {detail.lines.count()} dòng ngày")
    if mat:
        print(f"  KHNVL: {mat.code} · {mat.status} · {mat.lines.count()} dòng NPL")
    print("  URL: /san-xuat/ke-hoach/tong-the/  ·  /san-xuat/ke-hoach/chi-tiet/")


if __name__ == "__main__":
    main()
else:
    # python manage.py shell < file này
    main()
