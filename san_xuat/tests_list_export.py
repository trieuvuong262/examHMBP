"""Smoke tests xuat Excel danh sach San xuat."""

from django.test import RequestFactory, TestCase
from django.urls import reverse

from san_xuat.list_exports import LIST_EXPORT_REGISTRY, run_list_export


class _User:
    is_authenticated = True
    is_superuser = True
    is_staff = True
    pk = 1
    id = 1


class SanXuatListExportTests(TestCase):
    def test_registry_has_core_keys(self):
        for key in (
            "dispatch_mo",
            "capacity_list",
            "qc_sheet",
            "costing_order_list",
            "doc_list",
            "ncr_list",
        ):
            self.assertIn(key, LIST_EXPORT_REGISTRY)

    def test_list_export_url_resolves(self):
        url = reverse("san_xuat:list_export", kwargs={"export_key": "dispatch_mo"})
        self.assertIn("xuat-excel", url)
        self.assertIn("dispatch_mo", url)

    def test_run_list_export_dispatch_mo(self):
        req = RequestFactory().get("/san-xuat/xuat-excel/dispatch_mo/")
        req.user = _User()
        resp = run_list_export(req, "dispatch_mo")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp.get("Content-Type", ""))

    def test_run_list_export_capacity(self):
        req = RequestFactory().get("/san-xuat/xuat-excel/capacity_list/")
        req.user = _User()
        resp = run_list_export(req, "capacity_list")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp.get("Content-Type", ""))