from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from hrm.permissions import ROLE_DIRECTOR

from .models import TienDoItem


def _user(username, *, role=""):
    user = User.objects.create_user(username, password="pass")
    if role:
        profile = user.profile
        profile.role = role
        profile.save(update_fields=["role"])
    return user


class TienDoCompletionTests(TestCase):
    def setUp(self):
        self.owner = _user("td_owner")
        self.other = _user("td_other")
        self.director = _user("td_director", role=ROLE_DIRECTOR)
        self.item = TienDoItem.objects.create(
            platform=TienDoItem.PLATFORM_PORTAL,
            feature="Dang nhap",
            created_by=self.owner,
        )
        self.client = Client()

    def _post(self, user, url_name):
        self.client.force_login(user)
        return self.client.post(reverse(url_name, args=[self.item.pk]))

    @patch("assessment.decorators._user_can_module_action", return_value=True)
    def test_owner_completes_and_board_moves_to_collapsed_tab(self, _perm):
        response = self._post(self.owner, "tien_do:item_complete")
        self.assertEqual(response.status_code, 302)
        self.assertIn("tt=ht", response.url)
        self.item.refresh_from_db()
        self.assertIsNotNone(self.item.completed_at)
        self.assertEqual(self.item.completed_by_id, self.owner.id)

        done = self.client.get(reverse("tien_do:portal") + "?tt=ht")
        self.assertContains(done, "is-done is-collapsed")
        self.assertContains(done, "Dang nhap")
        self.assertContains(done, "Mở lại")

        open_tab = self.client.get(reverse("tien_do:portal"))
        self.assertNotContains(open_tab, "Dang nhap")

    @patch("assessment.decorators._user_can_module_action", return_value=True)
    def test_other_user_cannot_complete(self, _perm):
        response = self._post(self.other, "tien_do:item_complete")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("tt=ht", response.url)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.completed_at)

        board = self.client.get(reverse("tien_do:portal"))
        self.assertContains(board, "Dang nhap")
        self.assertNotContains(board, "jp-td-complete")

    @patch("assessment.decorators._user_can_module_action", return_value=True)
    def test_director_can_complete_and_reopen_any_item(self, _perm):
        response = self._post(self.director, "tien_do:item_complete")
        self.assertEqual(response.status_code, 302)
        self.assertIn("tt=ht", response.url)
        self.item.refresh_from_db()
        self.assertEqual(self.item.completed_by_id, self.director.id)

        response = self._post(self.director, "tien_do:item_reopen")
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("tt=ht", response.url)
        self.item.refresh_from_db()
        self.assertIsNone(self.item.completed_at)
        self.assertIsNone(self.item.completed_by_id)

    @patch("assessment.decorators._user_can_module_action", return_value=True)
    def test_owner_sees_complete_button(self, _perm):
        self.client.force_login(self.owner)
        board = self.client.get(reverse("tien_do:portal"))
        self.assertContains(board, "jp-td-complete")
        self.assertContains(board, "Hoàn thành")
