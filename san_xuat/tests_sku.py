"""Tests Style → SKU (Style + Color + Size)."""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from san_xuat.hub_models import (
    SxFgReceiptLine,
    SxGeneralSettings,
    SxProductionOrder,
    SxSku,
)
from san_xuat.models import BomVersion, ProductTechDoc
from san_xuat.services.dispatch import (
    DispatchError,
    confirm_stat,
    create_fg_receipt_from_mo,
    create_mo_from_bom,
    create_production_stat,
    mo_release,
)
from san_xuat.services.gates import MODE_BLOCK, MODE_OFF, MODE_WARN
from san_xuat.services.phase3 import Phase3Error, create_packing_record
from san_xuat.services.qc import create_request_from_stat
from san_xuat.services.sku_catalog import (
    compose_sku_code,
    expand_style_matrix,
    get_or_create_sku,
    parse_sku_code,
    resolve_sku_fields,
    seed_default_colors_sizes,
)


class SkuCatalogUnitTests(TestCase):
    def test_compose_sku_like_slide(self):
        self.assertEqual(
            compose_sku_code(style_code="JP-TEE-260001", color_code="NVY", size_label="M"),
            "JP-TEE-260001-NVY-M",
        )
        self.assertEqual(
            compose_sku_code(style_code="JP-TEE-260001", color_code="blk", size_label="l"),
            "JP-TEE-260001-BLK-L",
        )

    def test_parse_sku_with_style_dashes(self):
        parsed = parse_sku_code("JP-TEE-260001-NVY-M", style_hint="JP-TEE-260001")
        self.assertEqual(parsed, ("JP-TEE-260001", "NVY", "M"))

    def test_expand_matrix_5x7(self):
        seed_default_colors_sizes()
        colors = ["NVY", "BLK", "WHT", "GRY", "RED"]
        sizes = ["XS", "S", "M", "L", "XL", "XXL", "3XL"]
        rows = expand_style_matrix(
            style_code="JP-TEE-260001",
            color_codes=colors,
            size_labels=sizes,
            style_name="Tee demo",
        )
        self.assertEqual(len(rows), 35)
        self.assertTrue(SxSku.objects.filter(sku_code="JP-TEE-260001-NVY-M").exists())
        self.assertTrue(SxSku.objects.filter(sku_code="JP-TEE-260001-WHT-XL").exists())


class SkuWorkflowTests(TestCase):
    def setUp(self):
        seed_default_colors_sizes()
        self.user = User.objects.create_user("sku_tester", password="x")
        self.doc = ProductTechDoc.objects.create(
            product_code="JP-TEE-260001",
            product_name="Tee Navy demo",
            is_active=True,
        )
        self.bom = BomVersion.objects.create(
            tech_doc=self.doc,
            version_label="v1",
            status=BomVersion.STATUS_ACTIVE,
        )
        cfg = SxGeneralSettings.load()
        cfg.gate_sku_on_stat = MODE_WARN
        cfg.gate_sku_on_packing = MODE_WARN
        cfg.gate_issue_before_stat = MODE_OFF
        cfg.gate_stat_before_fg = MODE_OFF
        cfg.gate_qc_pass_before_fg = MODE_OFF
        cfg.gate_open_qc_alert_before_fg = MODE_OFF
        cfg.auto_create_qc_from_stat = False
        cfg.save()

    def _mo(self):
        mo = create_mo_from_bom(
            product_code="JP-TEE-260001",
            qty=Decimal("10"),
            team_label="Chuyen 1",
            user=self.user,
        )
        return mo_release(mo_id=mo.pk, user=self.user)

    def test_stat_resolves_sku_and_qc_copies(self):
        mo = self._mo()
        st = create_production_stat(
            production_order_id=mo.pk,
            stat_date=timezone.localdate(),
            process_name="May",
            qty_good=Decimal("5"),
            color_code="NVY",
            size_label="M",
            user=self.user,
        )
        self.assertEqual(st.sku_code, "JP-TEE-260001-NVY-M")
        self.assertEqual(st.color_code, "NVY")
        self.assertEqual(st.size_label, "M")
        self.assertIsNotNone(st.sku_id)
        st = confirm_stat(stat_id=st.pk)
        qc = create_request_from_stat(stat_id=st.pk, auto=False)
        self.assertEqual(qc.sku_code, "JP-TEE-260001-NVY-M")
        self.assertEqual(qc.color_code, "NVY")
        self.assertEqual(qc.size_label, "M")
        self.assertEqual(qc.sku_id, st.sku_id)

    def test_fg_receipt_line_from_stat_sku(self):
        mo = self._mo()
        st = create_production_stat(
            production_order_id=mo.pk,
            stat_date=timezone.localdate(),
            process_name="May",
            qty_good=Decimal("4"),
            color_code="BLK",
            size_label="L",
            user=self.user,
        )
        confirm_stat(stat_id=st.pk)
        mo.refresh_from_db()
        if mo.status == SxProductionOrder.STATUS_RELEASED:
            mo.status = SxProductionOrder.STATUS_IN_PROGRESS
            mo.save(update_fields=["status"])
        fg = create_fg_receipt_from_mo(production_order_id=mo.pk, stat_id=st.pk)
        lines = list(SxFgReceiptLine.objects.filter(receipt=fg))
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].sku_code, "JP-TEE-260001-BLK-L")
        self.assertEqual(lines[0].qty, Decimal("4"))

    def test_packing_lines_compose_sku(self):
        mo = self._mo()
        pack = create_packing_record(
            production_order_id=mo.pk,
            pack_date=timezone.localdate(),
            lines=[
                {"color_code": "WHT", "size_label": "XL", "qty": Decimal("3"), "carton_count": 1},
                {"color_code": "NVY", "size_label": "M", "qty": Decimal("2"), "carton_count": 1},
            ],
            user=self.user,
        )
        codes = set(pack.lines.values_list("sku_code", flat=True))
        self.assertEqual(codes, {"JP-TEE-260001-WHT-XL", "JP-TEE-260001-NVY-M"})
        self.assertEqual(pack.qty, Decimal("5"))

    def test_block_gate_requires_sku_on_stat(self):
        cfg = SxGeneralSettings.load()
        cfg.gate_sku_on_stat = MODE_BLOCK
        cfg.save(update_fields=["gate_sku_on_stat"])
        mo = self._mo()
        with self.assertRaises(DispatchError):
            create_production_stat(
                production_order_id=mo.pk,
                stat_date=timezone.localdate(),
                qty_good=Decimal("1"),
                user=self.user,
            )

    def test_block_gate_requires_sku_on_packing_line(self):
        cfg = SxGeneralSettings.load()
        cfg.gate_sku_on_packing = MODE_BLOCK
        cfg.save(update_fields=["gate_sku_on_packing"])
        mo = self._mo()
        with self.assertRaises(Phase3Error):
            create_packing_record(
                production_order_id=mo.pk,
                pack_date=timezone.localdate(),
                lines=[{"qty": Decimal("2"), "carton_count": 1}],
                user=self.user,
            )

    def test_resolve_from_sku_code_alone(self):
        get_or_create_sku(
            style_code="JP-TEE-260001",
            color_code="NVY",
            size_label="M",
        )
        resolved = resolve_sku_fields(
            style_code="JP-TEE-260001",
            sku_code="JP-TEE-260001-NVY-M",
        )
        self.assertEqual(resolved.color_code, "NVY")
        self.assertEqual(resolved.size_label, "M")
