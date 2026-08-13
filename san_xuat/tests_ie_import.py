"""Round-trip import nhom / thu vien cong doan / routing ma hang."""
from __future__ import annotations
import io
from decimal import Decimal
from django.test import TestCase
from san_xuat.ie_models import SxOperation, SxOperationGroup, SxRouting, SxRoutingLine
from san_xuat.services.operation_master import (
    KIND_GROUPS, KIND_LIBRARY, KIND_ROUTING,
    OperationMasterImportError, export_ie_dataset_workbook, import_ie_dataset,
)

def _as_upload(wb):
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

class IeDatasetImportTests(TestCase):
    def test_group_template_import_create_and_update(self):
        wb = export_ie_dataset_workbook(KIND_GROUPS, template=True)
        result = import_ie_dataset(_as_upload(wb), KIND_GROUPS)
        self.assertGreaterEqual(result.total_created, 1)
        grp = SxOperationGroup.objects.get(code="MAY")
        self.assertEqual(grp.name, "May")
        self.assertTrue(grp.is_active)
        self.assertEqual(grp.process_stage_label, "May")
        self.assertEqual(grp.product_part, "Cổ / thân")
        self.assertEqual(grp.data_owner, "IE")
        dry = import_ie_dataset(_as_upload(wb), KIND_GROUPS, dry_run=True)
        self.assertGreaterEqual(dry.total_created + dry.total_updated, 1)
        self.assertEqual(SxOperationGroup.objects.filter(code="MAY").count(), 1)
        again = import_ie_dataset(_as_upload(wb), KIND_GROUPS)
        self.assertEqual(again.created.get("group", 0), 0)
        self.assertGreaterEqual(again.updated.get("group", 0), 1)
        self.assertEqual(SxOperationGroup.objects.filter(code="MAY").count(), 1)

    def test_library_template_import_converts_seconds_to_smv(self):
        wb = export_ie_dataset_workbook(KIND_LIBRARY, template=True)
        result = import_ie_dataset(_as_upload(wb), KIND_LIBRARY)
        self.assertGreaterEqual(result.created.get("operation", 0), 2)
        op = SxOperation.objects.get(op_code="SEW-1001", op_rev="R01")
        self.assertEqual(op.name_vi, "May sống cổ áo (ví dụ)")
        self.assertEqual(op.base_smv_min, Decimal("0.6000"))
        self.assertEqual(op.status, SxOperation.STATUS_DRAFT)
        self.assertEqual(op.group.code, "MAY")
        op2 = SxOperation.objects.get(op_code="SEW-1002", op_rev="R01")
        self.assertEqual(op2.base_smv_min, Decimal("0.8000"))
        dry = import_ie_dataset(_as_upload(wb), KIND_LIBRARY, dry_run=True)
        self.assertFalse(dry.created)
        self.assertGreaterEqual(dry.updated.get("operation", 0), 2)

    def test_routing_template_import_lines_and_smv_minutes(self):
        import_ie_dataset(_as_upload(export_ie_dataset_workbook(KIND_LIBRARY, template=True)), KIND_LIBRARY)
        wb = export_ie_dataset_workbook(KIND_ROUTING, template=True)
        result = import_ie_dataset(_as_upload(wb), KIND_ROUTING)
        self.assertGreaterEqual(result.created.get("routing", 0), 1)
        self.assertGreaterEqual(result.created.get("routing_line", 0), 1)
        routing = SxRouting.objects.get(routing_id="STYLE-DEMO-R01")
        self.assertEqual(routing.style_code, "STYLE-DEMO")
        self.assertEqual(routing.routing_rev, "R01")
        self.assertTrue(routing.is_active)
        lines = list(routing.lines.order_by("seq_no"))
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertEqual(line.op_code, "SEW-1001")
        self.assertEqual(line.applied_unit_smv, Decimal("0.6000"))
        self.assertEqual(line.library_unit_smv, Decimal("0.6000"))
        self.assertEqual(line.qty_per_garment, Decimal("1.000"))
        self.assertEqual(line.total_operation_smv, Decimal("0.6000"))
        self.assertEqual(line.price_factor, Decimal("1.0000"))
        self.assertEqual(line.operation_id, SxOperation.objects.get(op_code="SEW-1001", op_rev="R01").pk)

    def test_round_trip_export_reimport_does_not_duplicate(self):
        import_ie_dataset(_as_upload(export_ie_dataset_workbook(KIND_GROUPS, template=True)), KIND_GROUPS)
        import_ie_dataset(_as_upload(export_ie_dataset_workbook(KIND_LIBRARY, template=True)), KIND_LIBRARY)
        import_ie_dataset(_as_upload(export_ie_dataset_workbook(KIND_ROUTING, template=True)), KIND_ROUTING)
        n_groups = SxOperationGroup.objects.count()
        n_ops = SxOperation.objects.count()
        n_rt = SxRouting.objects.count()
        n_lines = SxRoutingLine.objects.count()
        for kind in (KIND_GROUPS, KIND_LIBRARY, KIND_ROUTING):
            exported = export_ie_dataset_workbook(kind, template=False)
            import_ie_dataset(_as_upload(exported), kind)
        self.assertEqual(SxOperationGroup.objects.count(), n_groups)
        self.assertEqual(SxOperation.objects.count(), n_ops)
        self.assertEqual(SxRouting.objects.count(), n_rt)
        self.assertEqual(SxRoutingLine.objects.count(), n_lines)

    def test_wrong_sheet_raises(self):
        wb = export_ie_dataset_workbook(KIND_GROUPS, template=True)
        with self.assertRaises(OperationMasterImportError) as ctx:
            import_ie_dataset(_as_upload(wb), KIND_LIBRARY)
        self.assertIn("02_THU_VIEN_CONG_DOAN", str(ctx.exception))
