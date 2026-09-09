"""Tạo 1 ĐĐH xác nhận trên hàng đợi KHSX (local).

Chạy từ PortalJustPlay:
  python scripts/_seed_khsx_queue_test.py
"""

from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "PortalJustPlay.settings")
    import django

    django.setup()

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from san_xuat.hub_models import SxSalesOrder
from san_xuat.ie_models import SxRouting
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.order_routing import routings_for_product
from san_xuat.services.plan_board import recompute_plan_ranks
from san_xuat.services.plan_route import ensure_order_plan_steps
from san_xuat.services.sales_orders import LineInput, confirm_sales_order, create_sales_order

CODE = "DH-2026-KHSX-TEST"
NOTE = "[LOCAL] KHSX test — hàng đợi"


def _pick_product():
    for doc in ProductTechDoc.objects.filter(is_active=True).order_by("-id")[:80]:
        code = (doc.product_code or "").strip()
        if not code:
            continue
        bom = (
            BomVersion.objects.filter(tech_doc=doc)
            .prefetch_related("process_steps")
            .order_by("-id")
            .first()
        )
        if not bom:
            continue
        routing = None
        for rt in routings_for_product(code):
            if rt.lines.filter(applied_unit_smv__gt=0).exists():
                routing = rt
                break
        if routing is None:
            routing = (
                SxRouting.objects.filter(style_code__iexact=code, is_active=True)
                .order_by("-id")
                .first()
            )
        if bom.process_steps.exists() or routing:
            return doc, bom, routing
    return None, None, None


def run():
    with transaction.atomic():
        SxSalesOrder.objects.filter(code=CODE).delete()

        user = (
            get_user_model().objects.filter(is_superuser=True, is_active=True).order_by("id").first()
            or get_user_model().objects.filter(is_active=True).order_by("id").first()
        )
        doc, bom, routing = _pick_product()
        if not doc or not bom:
            raise RuntimeError("No product with BOM on local DB.")

        today = timezone.localdate()
        order = create_sales_order(
            code=CODE,
            customer_name="Khach test KHSX",
            request_date=today,
            due_date=today + timedelta(days=10),
            notes=NOTE,
            user=user,
            lines=[
                LineInput(
                    product_code=(doc.product_code or "").strip(),
                    product_name=doc.product_name or "",
                    qty=Decimal("24"),
                    bom_version_id=bom.pk,
                    routing_id=routing.pk if routing else None,
                ),
            ],
        )
        order = confirm_sales_order(order_id=order.pk, user=user)
        order.plan_priority = SxSalesOrder.PRIORITY_HIGH
        order.save(update_fields=["plan_priority", "updated_at"])
        ensure_order_plan_steps(order)
        n = recompute_plan_ranks()

    order.refresh_from_db()
    line = order.lines.get()
    print("OK KHSX test")
    print(
        f"  SO: {order.code}  confirm={order.confirm_status}  plan={order.plan_status}"
    )
    print(
        f"  priority={order.plan_priority}  rank={order.plan_rank}  "
        f"score={order.plan_score}  ranks_updated={n}"
    )
    print(f"  product: {line.product_code}  qty={line.qty}")
    print(
        f"  BOM=#{line.bom_version_id}  routing=#{line.routing_id}  "
        f"ops={line.routing_lines.count()}"
    )
    print("  URL: /san-xuat/ke-hoach/bang/?mode=list&tab=queue")


if __name__ == "__main__":
    run()
