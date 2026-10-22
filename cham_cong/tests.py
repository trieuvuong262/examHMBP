from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import RequestFactory, TestCase
from django.utils import timezone

from cham_cong.calc import (
    attendance_work_date,
    build_span,
    classify_day,
    distance_m,
    in_reminder_window,
    ip_matches_rule,
)
from cham_cong.models import Shift, ShiftAssignment, WorkSite, WorkSiteIp
from cham_cong.services import resolve_shift, verify_location
from hrm.models import Department, Division


class Policy:
    ot_weekday_rate = Decimal("1.50")
    ot_sunday_rate = Decimal("2.00")
    ot_holiday_rate = Decimal("3.00")


class OfficeShift:
    start_time = time(8, 0)
    end_time = time(17, 0)
    break_start = time(12, 0)
    break_end = time(13, 0)
    crosses_midnight = False
    late_grace_minutes = 5
    early_grace_minutes = 5
    saturday_start = time(8, 0)
    saturday_end = time(12, 0)


class NightShift:
    start_time = time(22, 0)
    end_time = time(6, 0)
    break_start = time(2, 0)
    break_end = time(2, 30)
    crosses_midnight = True
    late_grace_minutes = 5
    early_grace_minutes = 5
    saturday_start = time(22, 0)
    saturday_end = time(6, 0)


def aware(day, clock):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(day, clock), tz)


class CalcTests(TestCase):
    def test_full_office_day_is_one_cong(self):
        day = datetime(2026, 10, 22).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(
            aware(day, time(8, 0)),
            aware(day, time(17, 0)),
            None,
            None,
            span,
        )
        self.assertEqual(result["work_credit"], Decimal("1"))
        self.assertEqual(result["late_minutes"], 0)
        self.assertEqual(result["worked_minutes"], 8 * 60)
        self.assertEqual(result["status"], "complete")

    def test_late_inside_grace_is_not_late(self):
        day = datetime(2026, 10, 22).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(aware(day, time(8, 4)), aware(day, time(17, 0)), None, None, span)
        self.assertEqual(result["late_minutes"], 0)

    def test_late_and_overtime_keep_full_credit(self):
        day = datetime(2026, 10, 22).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(aware(day, time(8, 10)), aware(day, time(17, 20)), None, None, span)
        self.assertEqual(result["late_minutes"], 10)
        self.assertEqual(result["ot_minutes"], 20)
        self.assertEqual(result["ot_rate"], Decimal("1.50"))
        self.assertEqual(result["work_credit"], Decimal("1"))

    def test_morning_only_is_half_day(self):
        day = datetime(2026, 10, 22).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(aware(day, time(8, 0)), aware(day, time(12, 0)), None, None, span)
        self.assertEqual(result["work_credit"], Decimal("0.5"))

    def test_missing_clock_out_has_no_credit(self):
        day = datetime(2026, 10, 22).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(aware(day, time(8, 0)), None, None, None, span)
        self.assertIsNone(result["work_credit"])
        self.assertEqual(result["status"], "missing_out")

    def test_saturday_is_half_day(self):
        day = datetime(2026, 10, 24).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(aware(day, time(8, 0)), aware(day, time(12, 0)), None, None, span)
        self.assertEqual(result["work_credit"], Decimal("0.5"))
        self.assertEqual(result["day_kind"], "saturday")

    def test_sunday_and_holiday_rates(self):
        sunday = datetime(2026, 10, 25).date()
        span = build_span(OfficeShift(), sunday, is_holiday=False, policy=Policy())
        result = classify_day(aware(sunday, time(8, 0)), aware(sunday, time(12, 0)), None, None, span)
        self.assertEqual(result["work_credit"], Decimal("0"))
        self.assertEqual(result["ot_rate"], Decimal("2.00"))
        self.assertEqual(result["ot_minutes"], 4 * 60)
        holiday = build_span(OfficeShift(), sunday, is_holiday=True, policy=Policy())
        holiday_result = classify_day(
            aware(sunday, time(8, 0)), aware(sunday, time(12, 0)), None, None, holiday,
        )
        self.assertEqual(holiday_result["ot_rate"], Decimal("3.00"))

    def test_office_popup_window(self):
        day = datetime(2026, 10, 22).date()
        span = build_span(OfficeShift(), day, is_holiday=False, policy=Policy())
        self.assertTrue(in_reminder_window(span, aware(day, time(7, 0)), 60))
        self.assertTrue(in_reminder_window(span, aware(day, time(7, 59)), 60))
        self.assertFalse(in_reminder_window(span, aware(day, time(8, 0)), 60))
        self.assertFalse(in_reminder_window(span, aware(day, time(6, 59)), 60))

    def test_night_shift_work_date_and_credit(self):
        morning = aware(datetime(2026, 10, 23).date(), time(5, 0))
        self.assertEqual(attendance_work_date(NightShift(), morning), datetime(2026, 10, 22).date())
        day = datetime(2026, 10, 22).date()
        span = build_span(NightShift(), day, is_holiday=False, policy=Policy())
        result = classify_day(
            aware(day, time(22, 0)),
            aware(day + timedelta(days=1), time(6, 0)),
            None,
            None,
            span,
        )
        self.assertEqual(result["work_credit"], Decimal("1"))
        self.assertEqual(result["worked_minutes"], 7 * 60 + 30)

    def test_ip_and_distance(self):
        self.assertTrue(ip_matches_rule("203.0.113.8", "203.0.113.0/24"))
        self.assertFalse(ip_matches_rule("198.51.100.8", "203.0.113.0/24"))
        self.assertTrue(ip_matches_rule("203.0.113.8", "203.0.113.8"))
        self.assertLess(distance_m(10.762, 106.660, 10.762, 106.660), 1)


class LocationTests(TestCase):
    def test_wifi_ip_skips_gps_and_outside_radius_is_blocked(self):
        site = WorkSite.objects.create(
            name="Xuong 1", latitude="10.762000", longitude="106.660000", radius_m=100,
        )
        WorkSiteIp.objects.create(site=site, cidr="203.0.113.0/24")
        factory = RequestFactory()
        on_wifi = factory.post("/cham-cong/", REMOTE_ADDR="203.0.113.8")
        verified, error = verify_location(on_wifi)
        self.assertIsNone(error)
        self.assertEqual(verified["method"], "ip")

        on_mobile = factory.post("/cham-cong/", REMOTE_ADDR="198.51.100.9")
        blocked, blocked_error = verify_location(on_mobile, "21.028500", "105.854200")
        self.assertIsNone(blocked)
        self.assertIn("Ngoài bán kính", blocked_error)

        inside, inside_error = verify_location(on_mobile, "10.762100", "106.660100")
        self.assertIsNone(inside_error)
        self.assertEqual(inside["method"], "gps")
        self.assertLessEqual(inside["distance_m"], 100)

    def test_employee_shift_overrides_division(self):
        department = Department.objects.create(name="San xuat test cc")
        division = Division.objects.create(department=department, name="To may test cc")
        user = User.objects.create_user("cc_nv_test")
        profile = user.profile
        profile.department = department
        profile.division = division
        profile.is_employed = True
        profile.save()
        office = Shift.objects.create(
            name="Hanh chinh test", kind=Shift.KIND_OFFICE,
            start_time=time(8, 0), end_time=time(17, 0),
            saturday_start=time(8, 0), saturday_end=time(12, 0),
        )
        night = Shift.objects.create(
            name="Ca dem test", kind=Shift.KIND_PRODUCTION,
            start_time=time(22, 0), end_time=time(6, 0), crosses_midnight=True,
            saturday_start=time(22, 0), saturday_end=time(6, 0),
        )
        ShiftAssignment.objects.create(shift=office, division=division)
        self.assertEqual(resolve_shift(user), office)
        ShiftAssignment.objects.create(shift=night, user=user)
        self.assertEqual(resolve_shift(user), night)
