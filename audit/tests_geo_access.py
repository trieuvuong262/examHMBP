from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from audit.models import LoginSecurityConfig
from audit.services.geo_access import normalize_countries


class GeoCountryNormalizeTests(TestCase):
    def test_blank_means_vietnam(self):
        self.assertEqual(normalize_countries([]), ["VN"])
        self.assertEqual(normalize_countries(""), ["VN"])

    def test_unknown_code_falls_back_to_vietnam(self):
        self.assertEqual(normalize_countries(["US", "vn"]), ["VN"])


@patch("hrm.middleware.user_can_access_resolved_menu", return_value=True)
@patch("hrm.middleware.user_can_access_module", return_value=True)
@patch("assessment.decorators._user_can_module_action", return_value=True)
class GeoRegionViewTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_superuser("geoadmin", "geo@test.local", "pass")
        profile = getattr(user, "profile", None)
        if profile is not None and getattr(profile, "must_change_password", False):
            profile.must_change_password = False
            profile.save(update_fields=["must_change_password"])
        self.client.force_login(user)

    def test_region_tab_renders(self, _perm, _mod, _menu):
        response = self.client.get(reverse("audit:login_security") + "?tab=region")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Khu vực được kết nối VPS")
        self.assertContains(response, "Việt Nam")

    def test_apply_requires_confirm(self, _perm, _mod, _menu):
        response = self.client.post(reverse("audit:geo_region_save"), {"enabled": "on", "countries": "VN"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=region", response.url)
        self.assertFalse(LoginSecurityConfig.get_solo().geo_enabled)
