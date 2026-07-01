from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from hrm.avatar_permissions import (
    EXTRA_UPDATE_OWN_AVATAR,
    user_can_update_own_avatar,
    user_can_update_profile_avatar,
)
from hrm.forms import PermissionGroupPermissionForm
from hrm.group_permissions import normalize_module_entry
from hrm.models import PermissionGroup, Profile
from hrm.module_permissions import MODULE_HRM


class AvatarPermissionHelpersTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nv1", password="x")
        self.profile = Profile.objects.get(user=self.user)
        self.group = PermissionGroup.objects.create(
            slug="test-avatar-group",
            name="Test avatar",
            module_permissions={
                MODULE_HRM: {
                    "view": False,
                    "create": False,
                    "update": False,
                    "delete": False,
                    "export": False,
                    "extras": {EXTRA_UPDATE_OWN_AVATAR: True},
                },
            },
        )

    def test_own_avatar_requires_extra_or_hrm_update(self):
        self.assertFalse(user_can_update_own_avatar(self.user))
        self.profile.permission_group = self.group
        self.profile.save(update_fields=["permission_group"])
        self.assertTrue(user_can_update_own_avatar(self.user))

    def test_hr_can_update_other_avatar_without_extra(self):
        hr_user = User.objects.create_user(username="hr1", password="x")
        hr_profile = Profile.objects.get(user=hr_user)
        hr_group = PermissionGroup.objects.create(
            slug="test-hr-group",
            name="Test HR",
            module_permissions={
                MODULE_HRM: {
                    "view": True,
                    "create": True,
                    "update": True,
                    "delete": False,
                    "export": True,
                },
            },
        )
        hr_profile.permission_group = hr_group
        hr_profile.save(update_fields=["permission_group"])
        self.assertFalse(user_can_update_own_avatar(hr_user))
        self.assertTrue(user_can_update_profile_avatar(hr_user, self.profile))

    def test_normalize_preserves_hrm_extras(self):
        entry = normalize_module_entry(
            {"view": False, "update": False, "extras": {EXTRA_UPDATE_OWN_AVATAR: True}},
            module_key=MODULE_HRM,
        )
        self.assertTrue(entry.get("extras", {}).get(EXTRA_UPDATE_OWN_AVATAR))


class AvatarPermissionViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="nv2", password="x")
        self.profile = Profile.objects.get(user=self.user)


    @staticmethod
    def _sample_jpeg_bytes(width=64, height=64):
        from io import BytesIO
        from PIL import Image
        buf = BytesIO()
        Image.new("RGB", (width, height), color=(220, 38, 38)).save(buf, format="JPEG")
        return buf.getvalue()

    def _jpeg(self):
        return SimpleUploadedFile("me.jpg", self._sample_jpeg_bytes(), content_type="image/jpeg")


    @override_settings(MEDIA_ROOT="/tmp/jp-test-media")
    def test_update_avatar_denied_without_permission(self):
        self.client.login(username="nv2", password="x")
        response = self.client.post(reverse("update_avatar"), {"avatar": self._jpeg(), "next": "/"})
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.avatar)

    @override_settings(MEDIA_ROOT="/tmp/jp-test-media")
    def test_update_avatar_allowed_with_extra(self):
        group = PermissionGroup.objects.create(
            slug="test-avatar-allowed",
            name="Avatar allowed",
            module_permissions={MODULE_HRM: {"extras": {EXTRA_UPDATE_OWN_AVATAR: True}}},
        )
        self.profile.permission_group = group
        self.profile.save(update_fields=["permission_group"])
        self.client.login(username="nv2", password="x")
        response = self.client.post(reverse("update_avatar"), {"avatar": self._jpeg(), "next": "/"})
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.avatar)


class AvatarPermissionFormTests(TestCase):
    def test_form_roundtrip_hrm_extra(self):
        form = PermissionGroupPermissionForm(initial_permissions={MODULE_HRM: {"extras": {EXTRA_UPDATE_OWN_AVATAR: True}}})
        data = {field_name: field.initial or False for field_name, field in form.fields.items()}
        data["extra_hrm_update_own_avatar"] = True
        form = PermissionGroupPermissionForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        perms = form.cleaned_permissions()
        self.assertTrue(perms[MODULE_HRM].get("extras", {}).get(EXTRA_UPDATE_OWN_AVATAR))
