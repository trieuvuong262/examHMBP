from django.contrib.auth.models import User
from django.test import TestCase

from company_trip.constants import ROOM_2, ROOM_3, ROOM_ORGANIZER
from company_trip.forms import TripRegistrationForm
from company_trip.models import SpinNumber
from hrm.models import Profile


def _profile(user, name):
    profile = Profile.objects.get(user=user)
    profile.full_name = name
    profile.is_employed = True
    profile.save(update_fields=["full_name", "is_employed"])
    return profile


class TripRoomFormTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", "o@x.test", "x")
        self.a = User.objects.create_user("ua", "a@x.test", "x")
        self.b = User.objects.create_user("ub", "b@x.test", "x")
        self.owner_p = _profile(self.owner, "Owner")
        self.pa = _profile(self.a, "Ban A")
        self.pb = _profile(self.b, "Ban B")

    def _form(self, room, c1=None, c2=None):
        data = {
            "phone": "0900000000",
            "room_type": room,
            "vegetarian": "Khong an chay" if False else "Không ăn chay",
            "breakfast_choice": "Không ăn sáng",
            "route": "Tham quan Vịnh Vĩnh Hy",
            "shopping": "Tham gia",
        }
        if c1:
            data["companion1_id"] = c1
        if c2:
            data["companion2_id"] = c2
        return TripRegistrationForm(data, current_profile=self.owner_p)

    def test_room2_requires_one_companion(self):
        self.assertFalse(self._form(ROOM_2).is_valid())

    def test_room2_accepts_one_companion(self):
        form = self._form(ROOM_2, c1=self.pa.pk)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["companion1_obj"], self.pa)
        self.assertIsNone(form.cleaned_data["companion2_obj"])

    def test_room3_requires_two_companions(self):
        self.assertFalse(self._form(ROOM_3, c1=self.pa.pk).is_valid())

    def test_room3_accepts_two_companions(self):
        form = self._form(ROOM_3, c1=self.pa.pk, c2=self.pb.pk)
        self.assertTrue(form.is_valid(), form.errors)

    def test_room3_rejects_duplicate_companions(self):
        self.assertFalse(self._form(ROOM_3, c1=self.pa.pk, c2=self.pa.pk).is_valid())

    def test_organizer_clears_companions(self):
        form = self._form(ROOM_ORGANIZER, c1=self.pa.pk)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["companion1_obj"])


class LuckySpinApiTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("admin_spin", "s@x.test", "x")
        self.admin.is_staff = True
        self.admin.save(update_fields=["is_staff"])
        self.client.force_login(self.admin)

    def test_check_lucky_returns_lucky_first_and_marks_shown(self):
        SpinNumber.objects.create(number=7, lucky=False, shown=False)
        SpinNumber.objects.create(number=42, lucky=True, shown=False)
        res = self.client.get("/tien-ich/vong-quay/api/check_lucky/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["has_lucky"])
        self.assertEqual(data["number"], "042")
        self.assertTrue(SpinNumber.objects.get(number=42).shown)

    def test_spin_prefers_unshown_lucky(self):
        SpinNumber.objects.create(number=1, lucky=False, shown=False)
        SpinNumber.objects.create(number=9, lucky=True, shown=False)
        res = self.client.get("/tien-ich/vong-quay/spin/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["result"], "009")
        self.assertTrue(SpinNumber.objects.get(number=9).shown)

    def test_non_staff_blocked(self):
        user = User.objects.create_user("nv", "n@x.test", "x")
        self.client.force_login(user)
        res = self.client.get("/tien-ich/vong-quay/spin/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertIn(res.status_code, (302, 403))
