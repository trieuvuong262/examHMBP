from datetime import date, datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from hrm.models import Department, DepartmentMenuPermission, Profile, RoleModulePermission
from hrm.permissions import ROLE_EMPLOYEE, ROLE_TEAM_LEADER
from reports.models import (
    DailyWorkReport,
    ProductionHourlyQuantity,
    ProductionShiftProduct,
)
from reports.production_shift_policy import (
    ProductionShiftReassignError,
    reassign_production_report_shift,
)
from reports.report_profile import REPORT_PROFILE_PRODUCTION


class ProductionShiftReassignTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(
            name="SX Shift Edit",
            sort_order=1,
            report_profile=REPORT_PROFILE_PRODUCTION,
        )
        DepartmentMenuPermission.objects.create(department=self.dept, modules=["reports"])
        perms = {"reports": {"view": True, "edit": True, "create": True, "update": True}}
        for role in (ROLE_EMPLOYEE, ROLE_TEAM_LEADER):
            RoleModulePermission.objects.update_or_create(
                role=role,
                defaults={"module_permissions": perms},
            )
        self.leader = self._user("ldr_shift_edit", ROLE_TEAM_LEADER)
        self.member = self._user("mem_shift_edit", ROLE_EMPLOYEE)
        self.leader.profile.subordinates.add(self.member)
        self.report_date = date(2026, 10, 21)
        self.client = Client(HTTP_HOST="testserver")

    def _user(self, username, role):
        user = User.objects.create_user(username=username, password="test")
        Profile.objects.filter(user=user).update(
            department=self.dept,
            role=role,
            full_name=username,
            is_employed=True,
        )
        user.refresh_from_db()
        return user

    def _report(self, shift=DailyWorkReport.SHIFT_MORNING):
        report = DailyWorkReport.objects.create(
            employee=self.member,
            report_date=self.report_date,
            report_profile=REPORT_PROFILE_PRODUCTION,
            shift=shift,
            status=DailyWorkReport.STATUS_SUBMITTED,
            submitted_at=timezone.now(),
        )
        product = ProductionShiftProduct.objects.create(
            report=report,
            product_code="PEGASUS",
            process_name="MAY",
            status=ProductionShiftProduct.STATUS_DONE,
            first_slot_index=9,
            total_quantity=Decimal("12"),
            started_at=timezone.make_aware(datetime(2026, 10, 21, 18, 0)),
            ended_at=timezone.make_aware(datetime(2026, 10, 21, 19, 0)),
        )
        ProductionHourlyQuantity.objects.create(
            product=product,
            slot_index=9,
            quantity=Decimal("12"),
            note="ot",
        )
        return report

    def test_morning_overtime_hour_moves_to_night_slot(self):
        report = self._report()
        old_label, new_label = reassign_production_report_shift(
            report, DailyWorkReport.SHIFT_NIGHT,
        )
        self.assertEqual(old_label, "Ca sáng")
        self.assertEqual(new_label, "Ca tối")
        report.refresh_from_db()
        self.assertEqual(report.shift, DailyWorkReport.SHIFT_NIGHT)
        entry = ProductionHourlyQuantity.objects.get()
        self.assertEqual(entry.slot_index, 1)
        self.assertEqual(entry.quantity, Decimal("12"))
        self.assertEqual(entry.note, "ot")
        self.assertEqual(entry.product.first_slot_index, 1)

    def test_rejects_hours_outside_target_shift(self):
        report = self._report()
        entry = ProductionHourlyQuantity.objects.get()
        entry.slot_index = 0
        entry.save(update_fields=["slot_index"])
        with self.assertRaises(ProductionShiftReassignError):
            reassign_production_report_shift(report, DailyWorkReport.SHIFT_NIGHT)
        report.refresh_from_db()
        self.assertEqual(report.shift, DailyWorkReport.SHIFT_MORNING)
        self.assertEqual(ProductionHourlyQuantity.objects.get().slot_index, 0)

    def test_leader_popup_changes_shift(self):
        report = self._report()
        self.client.login(username="ldr_shift_edit", password="test")
        url = reverse("reports:detail_cn", args=[report.pk])
        page = self.client.get(url)
        self.assertContains(page, "Sửa ca")
        self.assertContains(page, "prodShiftEditModal")
        response = self.client.post(url, {"action": "change_shift", "shift": "NIGHT"})
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertEqual(report.shift, DailyWorkReport.SHIFT_NIGHT)
        self.assertTrue(report.edit_logs.filter(summary__contains="Ca tối").exists())
