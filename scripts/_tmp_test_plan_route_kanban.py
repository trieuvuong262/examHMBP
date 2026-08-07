# -*- coding: utf-8 -*-
"""Smoke test Kanban lo trinh ke hoach SX tren VPS."""
from __future__ import annotations

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from san_xuat.hub_models import (
    SxMoProcessStep,
    SxProductionOrder,
    SxSalesOrder,
    SxSalesOrderLine,
    SxSalesOrderPlanStep,
    SxWorkCenter,
)
from san_xuat.services.plan_route import (
    AXIS_DAY,
    AXIS_PROCESS,
    AXIS_TEAM,
    UNASSIGNED_KEY,
    build_kanban,
    ensure_order_plan_steps,
    move_kanban_card,
    replace_order_plan_steps,
)
from san_xuat.services.work_calendar import working_days

HOST = "portal.justplay.vn"
fails = []


def ok(label, cond, detail=""):
    if cond:
        print(f"PASS {label}" + (f" | {detail}" if detail else ""))
    else:
        print(f"FAIL {label}" + (f" | {detail}" if detail else ""))
        fails.append(label)


User = get_user_model()
u = User.objects.filter(is_superuser=True).first() or User.objects.first()
ok("user", bool(u), getattr(u, "username", ""))

c = Client()
c.force_login(u)

for tab in ("day", "process", "team"):
    r = c.get(
        "/san-xuat/ke-hoach/bang/",
        {"mode": "route", "tab": tab},
        HTTP_HOST=HOST,
    )
    body = r.content or b""
    ok(f"http_route_{tab}", r.status_code == 200, str(r.status_code))
    ok(f"has_kb_board_{tab}", b"jp-kb-board" in body)
    ok(f"has_kb_col_{tab}", b"jp-kb-col" in body)

r_list = c.get("/san-xuat/ke-hoach/bang/", {"mode": "list", "tab": "queue"}, HTTP_HOST=HOST)
ok("http_list_queue", r_list.status_code == 200, str(r_list.status_code))
ok("list_has_lo_trinh_btn", b"mode=route" in (r_list.content or b""))

# --- service: seed + move on a queued confirmed order ---
order = (
    SxSalesOrder.objects.filter(
        is_demo=False,
        confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
        plan_status__in=("queued", "ranked", "on_hold"),
    )
    .exclude(production_orders__is_demo=False)
    .order_by("-id")
    .first()
)
# Prefer order without open MO
if order and order.production_orders.filter(is_demo=False).exclude(
    status=SxProductionOrder.STATUS_CANCELLED
).exists():
    order = (
        SxSalesOrder.objects.filter(
            is_demo=False,
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status__in=("queued", "ranked"),
        )
        .order_by("-id")
        .first()
    )
    if order and order.production_orders.filter(is_demo=False).exclude(
        status=SxProductionOrder.STATUS_CANCELLED
    ).exists():
        # create disposable test order from existing product line if possible
        order = None

created_temp = False
if order is None:
    # Find any product with BOM-ish line from recent orders
    src_line = SxSalesOrderLine.objects.filter(order__is_demo=False).order_by("-id").first()
    if src_line:
        order = SxSalesOrder.objects.create(
            code=f"TEST-KB-{timezone.now().strftime('%H%M%S')}",
            customer_name="Kanban smoke",
            request_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=7),
            confirm_status=SxSalesOrder.CONFIRM_CONFIRMED,
            plan_status=SxSalesOrder.PLAN_QUEUED,
            plan_queued_at=timezone.now(),
            is_demo=False,
        )
        SxSalesOrderLine.objects.create(
            order=order,
            product_code=src_line.product_code,
            product_name=src_line.product_name or "",
            qty=src_line.qty or 1,
            sort_order=0,
        )
        created_temp = True
        print("INFO created temp order", order.code, src_line.product_code)

ok("queue_order", bool(order), getattr(order, "code", ""))

if order:
    steps = ensure_order_plan_steps(order)
    ok("ensure_steps", True, f"n={len(steps)}")

    # If no routing, inject one step manually
    if not steps:
        wc = SxWorkCenter.objects.filter(is_active=True, is_demo=False).first()
        steps = replace_order_plan_steps(
            order_id=order.pk,
            steps=[{
                "sequence": 10,
                "process_name": "Cat",
                "work_center_id": wc.pk if wc else None,
            }],
        )
        ok("inject_step", len(steps) == 1, str(len(steps)))

    step = steps[0]
    today = timezone.localdate()
    days = working_days(today, today + timedelta(days=21))
    target_day = days[1] if len(days) > 1 else (days[0] if days else today)

    card = move_kanban_card(
        card_type="order",
        card_id=step.pk,
        axis=AXIS_DAY,
        target_key=target_day.isoformat(),
    )
    step.refresh_from_db()
    ok("move_day", step.planned_date == target_day, str(step.planned_date))

    # move process
    new_name = "May" if (step.process_name or "").casefold() != "may" else "QC"
    card = move_kanban_card(
        card_type="order",
        card_id=step.pk,
        axis=AXIS_PROCESS,
        target_key=new_name,
    )
    step.refresh_from_db()
    ok("move_process", step.process_name == new_name, step.process_name)

    # move team
    wc = SxWorkCenter.objects.filter(is_active=True, is_demo=False).exclude(
        pk=step.work_center_id or 0
    ).first() or SxWorkCenter.objects.filter(is_active=True, is_demo=False).first()
    if wc:
        move_kanban_card(
            card_type="order",
            card_id=step.pk,
            axis=AXIS_TEAM,
            target_key=str(wc.pk),
        )
        step.refresh_from_db()
        ok("move_team", step.work_center_id == wc.pk, str(step.work_center_id))
    else:
        ok("move_team", False, "no work center")

    # unassign day
    move_kanban_card(
        card_type="order",
        card_id=step.pk,
        axis=AXIS_DAY,
        target_key=UNASSIGNED_KEY,
    )
    step.refresh_from_db()
    ok("move_day_unassign", step.planned_date is None, str(step.planned_date))

    # replace route
    replaced = replace_order_plan_steps(
        order_id=order.pk,
        steps=[
            {"sequence": 10, "process_name": "Cat", "planned_date": target_day.isoformat()},
            {"sequence": 20, "process_name": "May", "work_center_id": wc.pk if wc else None},
        ],
    )
    ok("replace_route", len(replaced) == 2, str(len(replaced)))

    board = build_kanban(axis=AXIS_DAY, days=14)
    n_cards = sum(len(col.cards) for col in board.columns)
    ok("build_kanban_day", n_cards >= 1, f"cards={n_cards} cols={len(board.columns)}")

    board_p = build_kanban(axis=AXIS_PROCESS, days=14)
    ok("build_kanban_process", len(board_p.columns) >= 1, f"cols={len(board_p.columns)}")

    board_t = build_kanban(axis=AXIS_TEAM, days=14)
    ok("build_kanban_team", len(board_t.columns) >= 1, f"cols={len(board_t.columns)}")

    # AJAX move_card
    step2 = order.plan_steps.order_by("sequence").first()
    resp = c.post(
        "/san-xuat/ke-hoach/bang/?mode=route&tab=day",
        {
            "action": "move_card",
            "mode": "route",
            "axis": "day",
            "card_type": "order",
            "card_id": str(step2.pk),
            "target_key": target_day.isoformat(),
        },
        HTTP_HOST=HOST,
        HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        HTTP_ACCEPT="application/json",
    )
    ok("ajax_move", resp.status_code == 200, f"{resp.status_code} {resp.content[:120]!r}")

# MO step move if any open
mo_step = (
    SxMoProcessStep.objects.filter(production_order__is_demo=False)
    .exclude(production_order__status=SxProductionOrder.STATUS_CANCELLED)
    .exclude(production_order__status=SxProductionOrder.STATUS_DONE)
    .select_related("production_order")
    .first()
)
if mo_step:
    before = mo_step.planned_date
    days = working_days(timezone.localdate(), timezone.localdate() + timedelta(days=21))
    d = days[0] if days else timezone.localdate()
    move_kanban_card(card_type="mo", card_id=mo_step.pk, axis=AXIS_DAY, target_key=d.isoformat())
    mo_step.refresh_from_db()
    ok("mo_move_day", mo_step.planned_date == d, f"{before} -> {mo_step.planned_date}")
    # restore
    if before:
        move_kanban_card(card_type="mo", card_id=mo_step.pk, axis=AXIS_DAY, target_key=before.isoformat())
    else:
        move_kanban_card(card_type="mo", card_id=mo_step.pk, axis=AXIS_DAY, target_key=UNASSIGNED_KEY)
else:
    print("SKIP mo_move_day | no open MO step")

# cleanup temp order
if created_temp and order:
    oid = order.pk
    order.plan_steps.all().delete()
    order.lines.all().delete()
    order.delete()
    ok("cleanup_temp", not SxSalesOrder.objects.filter(pk=oid).exists())

print("----")
if fails:
    print("RESULT FAIL", len(fails), fails)
else:
    print("RESULT OK")
