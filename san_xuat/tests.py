from decimal import Decimal

from django.test import TestCase

from kho_npl.models import Material, MaterialCategory, Unit
from san_xuat.models import BomLine, BomVersion, ProcessStep, ProductTechDoc
from san_xuat.services.bom import activate_bom, create_tech_doc, ensure_single_active, BomError
from san_xuat.services.costing import compute_costing, labor_cost_for_step


class SanXuatCostingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.unit = Unit.objects.create(code='M', name='Met')
        cls.cat = MaterialCategory.objects.create(code='VAI', name='Vai')
        cls.mat = Material.objects.create(
            code='TEST-VAI-001',
            name='VAI TEST',
            category=cls.cat,
            unit=cls.unit,
            base_price=Decimal('100000'),
        )
        cls.doc = ProductTechDoc.objects.create(
            product_code='TEST-SP-001',
            product_name='Ao test',
        )
        cls.bom = BomVersion.objects.create(
            tech_doc=cls.doc,
            version_label='v1',
            status=BomVersion.STATUS_DRAFT,
            overhead_pct=Decimal('10'),
        )
        BomLine.objects.create(
            bom=cls.bom,
            material=cls.mat,
            qty=Decimal('1.2'),
            scrap_pct=Decimal('5'),
            sort_order=10,
        )
        ProcessStep.objects.create(
            bom=cls.bom,
            sequence=10,
            process_name='May',
            norm_per_hour=Decimal('10'),
            cost_per_hour=Decimal('50000'),
        )

    def test_labor_formula(self):
        hours, amount = labor_cost_for_step(Decimal('10'), Decimal('50000'))
        self.assertEqual(amount, Decimal('5000.00'))
        self.assertEqual(hours, Decimal('0.100000'))

    def test_compute_costing_material_and_labor(self):
        result = compute_costing(self.bom)
        self.assertEqual(result.material_cost, Decimal('126000.00'))
        self.assertEqual(result.labor_cost, Decimal('5000.00'))
        self.assertEqual(result.overhead_cost, Decimal('13100.00'))
        self.assertEqual(result.total_cost, Decimal('144100.00'))
        self.assertEqual(len(result.material_lines), 1)
        self.assertEqual(len(result.process_lines), 1)


class SanXuatBomActiveTests(TestCase):
    def setUp(self):
        self.doc = ProductTechDoc.objects.create(product_code='TEST-SP-002', product_name='SP2')
        self.bom1 = BomVersion.objects.create(
            tech_doc=self.doc,
            version_label='v1',
            status=BomVersion.STATUS_DRAFT,
        )
        self.bom2 = BomVersion.objects.create(
            tech_doc=self.doc,
            version_label='v2',
            status=BomVersion.STATUS_DRAFT,
        )

    def test_activate_archives_previous(self):
        activate_bom(self.bom1)
        self.bom1.refresh_from_db()
        self.assertEqual(self.bom1.status, BomVersion.STATUS_ACTIVE)
        activate_bom(self.bom2)
        self.bom1.refresh_from_db()
        self.bom2.refresh_from_db()
        self.assertEqual(self.bom1.status, BomVersion.STATUS_ARCHIVED)
        self.assertEqual(self.bom2.status, BomVersion.STATUS_ACTIVE)
        self.assertEqual(
            self.doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE).count(),
            1,
        )

    def test_ensure_single_active(self):
        self.bom1.status = BomVersion.STATUS_ACTIVE
        self.bom1.save(update_fields=['status'])
        self.bom2.status = BomVersion.STATUS_ACTIVE
        self.bom2.save(update_fields=['status'])
        ensure_single_active(self.doc)
        actives = list(self.doc.bom_versions.filter(status=BomVersion.STATUS_ACTIVE))
        self.assertEqual(len(actives), 1)

    def test_create_tech_doc_duplicate(self):
        create_tech_doc(product_code='TEST-SP-003')
        with self.assertRaises(BomError):
            create_tech_doc(product_code='TEST-SP-003')


class HubOverviewTests(TestCase):
    """Hub Portal scaffold — không đụng kho_npl."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        cls.admin = User.objects.create_superuser(
            username='sx_hub_admin',
            password='pass12345',
            email='sxhub@test.local',
        )

    def test_hub_redirects_to_overview(self):
        self.client.force_login(self.admin)
        r = self.client.get('/san-xuat/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/san-xuat/tong-quan/', r.url)

    def test_overview_ok(self):
        self.client.force_login(self.admin)
        r = self.client.get('/san-xuat/tong-quan/')
        self.assertEqual(r.status_code, 200)

    def test_stubs_ok(self):
        self.client.force_login(self.admin)
        for path in (
            '/san-xuat/ke-hoach/',
            '/san-xuat/dieu-phoi/',
            '/san-xuat/chat-luong/',
            '/san-xuat/quy-trinh/',
        ):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)

    def test_doc_list_still_works(self):
        self.client.force_login(self.admin)
        r = self.client.get('/san-xuat/ho-so/')
        self.assertEqual(r.status_code, 200)

    def test_npl_redirect(self):
        self.client.force_login(self.admin)
        r = self.client.get('/san-xuat/kho-npl/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/kho-npl/', r.url)

