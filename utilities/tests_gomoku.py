import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from utilities.gomoku import (
    GomokuError,
    create_room,
    elo_change,
    has_five,
    history_for,
    join_room,
    leaderboard,
    leave_room,
    offer_draw,
    place_move,
    request_rematch,
    resign,
    respond_draw,
    state_for,
    sync_room,
)
from utilities.models import GomokuGame, GomokuRoom, GomokuStats, gomoku_empty_board

User = get_user_model()


def _line(board, row, col, stone, count, dr, dc):
    for step in range(count):
        board[row + dr * step][col + dc * step] = stone
    return board


class GomokuRuleTests(TestCase):
    def test_five_in_four_directions_and_overline(self):
        stone = 1
        horizontal = _line(gomoku_empty_board(), 7, 2, stone, 5, 0, 1)
        self.assertTrue(has_five(horizontal, 7, 4))
        vertical = _line(gomoku_empty_board(), 1, 3, stone, 5, 1, 0)
        self.assertTrue(has_five(vertical, 3, 3))
        diagonal = _line(gomoku_empty_board(), 2, 2, stone, 5, 1, 1)
        self.assertTrue(has_five(diagonal, 4, 4))
        anti = _line(gomoku_empty_board(), 2, 10, stone, 5, 1, -1)
        self.assertTrue(has_five(anti, 6, 6))
        overline = _line(gomoku_empty_board(), 0, 0, stone, 6, 0, 1)
        self.assertTrue(has_five(overline, 0, 5))
        four = _line(gomoku_empty_board(), 8, 8, stone, 4, 0, 1)
        self.assertFalse(has_five(four, 8, 11))

    def test_elo_even_game_is_sixteen(self):
        self.assertEqual(elo_change(1000, 1000, 1), 16)
        self.assertEqual(elo_change(1000, 1000, 0), -16)
        self.assertEqual(elo_change(1000, 1000, 0.5), 0)


class GomokuRoomTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.host = User.objects.create_user(username='caro_host', password='test')
        self.guest = User.objects.create_user(username='caro_guest', password='test')
        self.host.profile.full_name = 'Chu Phong'
        self.host.profile.save(update_fields=['full_name'])
        self.guest.profile.full_name = 'Khach Vao'
        self.guest.profile.save(update_fields=['full_name'])

    def _start(self):
        room = create_room(self.host, now=self.now)
        return join_room(self.guest, room.code, now=self.now)

    def test_create_join_and_one_open_room(self):
        room = create_room(self.host, now=self.now)
        self.assertEqual(len(room.code), 4)
        self.assertTrue(room.code.isdigit())
        with self.assertRaises(GomokuError):
            create_room(self.host, now=self.now)
        with self.assertRaises(GomokuError):
            join_room(self.host, room.code, now=self.now)
        playing = join_room(self.guest, room.code, now=self.now)
        self.assertEqual(playing.status, GomokuRoom.STATUS_PLAYING)
        self.assertEqual(playing.host_color, GomokuRoom.COLOR_BLACK)
        self.assertEqual(playing.turn, GomokuRoom.COLOR_BLACK)
        self.assertEqual(playing.guest_id, self.guest.pk)
        other = User.objects.create_user(username='caro_third', password='test')
        with self.assertRaises(GomokuError):
            join_room(other, room.code, now=self.now)
        with self.assertRaises(GomokuError):
            create_room(self.guest, now=self.now)

    def test_win_updates_elo_and_names(self):
        self._start()
        for col in range(4):
            place_move(self.host, 7, col, now=self.now)
            place_move(self.guest, 8, col, now=self.now)
        room = place_move(self.host, 7, 4, now=self.now)
        self.assertEqual(room.status, GomokuRoom.STATUS_FINISHED)
        host_stats = GomokuStats.objects.get(user=self.host)
        guest_stats = GomokuStats.objects.get(user=self.guest)
        self.assertEqual(host_stats.wins, 1)
        self.assertEqual(host_stats.elo, 1016)
        self.assertEqual(guest_stats.losses, 1)
        self.assertEqual(guest_stats.elo, 984)
        board = leaderboard(self.host)
        self.assertEqual(board[0]['name'], 'Chu Phong')
        self.assertEqual(board[0]['elo'], 1016)
        story = history_for(self.guest)
        self.assertEqual(story[0]['opponent'], 'Chu Phong')
        self.assertEqual(story[0]['outcome'], 'loss')
        self.assertEqual(story[0]['elo_delta'], -16)

    def test_not_your_turn_and_occupied_cell(self):
        self._start()
        place_move(self.host, 0, 0, now=self.now)
        with self.assertRaises(GomokuError):
            place_move(self.host, 0, 1, now=self.now)
        with self.assertRaises(GomokuError):
            place_move(self.guest, 0, 0, now=self.now)

    def test_resign_and_rematch_swaps_colors(self):
        self._start()
        room = resign(self.host, now=self.now)
        self.assertEqual(room.status, GomokuRoom.STATUS_FINISHED)
        self.assertEqual(GomokuStats.objects.get(user=self.guest).wins, 1)
        request_rematch(self.host, now=self.now)
        still = GomokuRoom.objects.get(pk=room.pk)
        self.assertEqual(still.status, GomokuRoom.STATUS_FINISHED)
        self.assertTrue(still.host_rematch)
        again = request_rematch(self.guest, now=self.now)
        self.assertEqual(again.status, GomokuRoom.STATUS_PLAYING)
        self.assertEqual(again.host_color, GomokuRoom.COLOR_WHITE)
        self.assertEqual(again.turn, GomokuRoom.COLOR_BLACK)
        self.assertEqual(again.move_count, 0)
        payload = state_for(self.guest, now=self.now)['room']
        self.assertTrue(payload['your_turn'])
        self.assertEqual(payload['your_color'], 'black')

    def test_draw_offer_accept_and_decline(self):
        self._start()
        offer_draw(self.guest, now=self.now)
        with self.assertRaises(GomokuError):
            respond_draw(self.guest, True, now=self.now)
        declined = respond_draw(self.host, False, now=self.now)
        self.assertIsNone(declined.draw_offer_by_id)
        self.assertEqual(declined.status, GomokuRoom.STATUS_PLAYING)
        offer_draw(self.host, now=self.now)
        agreed = respond_draw(self.guest, True, now=self.now)
        self.assertEqual(agreed.status, GomokuRoom.STATUS_FINISHED)
        self.assertEqual(GomokuStats.objects.get(user=self.host).draws, 1)
        self.assertEqual(GomokuStats.objects.get(user=self.host).elo, 1000)
        game = GomokuGame.objects.get()
        self.assertEqual(game.reason, GomokuGame.REASON_DRAW)

    def test_move_declines_draw_offer(self):
        self._start()
        offer_draw(self.guest, now=self.now)
        room = place_move(self.host, 4, 4, now=self.now)
        self.assertIsNone(room.draw_offer_by_id)
        self.assertEqual(room.turn, GomokuRoom.COLOR_WHITE)

    def test_timeout_counts_as_loss_even_with_draw_offer(self):
        room = self._start()
        offer_draw(self.guest, now=self.now)
        later = self.now + timedelta(seconds=61)
        synced = sync_room(room, now=later)
        self.assertEqual(synced.status, GomokuRoom.STATUS_FINISHED)
        game = GomokuGame.objects.get()
        self.assertEqual(game.reason, GomokuGame.REASON_TIMEOUT)
        self.assertEqual(game.result, GomokuGame.RESULT_WHITE)
        self.assertEqual(GomokuStats.objects.get(user=self.host).losses, 1)

    def test_leave_waiting_does_not_score_and_frees_code(self):
        room = create_room(self.host, now=self.now)
        leave_room(self.host, now=self.now)
        self.assertFalse(GomokuStats.objects.filter(wins__gt=0).exists())
        self.assertEqual(GomokuRoom.objects.get(pk=room.pk).status, GomokuRoom.STATUS_CLOSED)
        again = create_room(self.host, now=self.now)
        self.assertEqual(len(again.code), 4)

    def test_leave_while_playing_is_rejected(self):
        self._start()
        with self.assertRaises(GomokuError):
            leave_room(self.host, now=self.now)

    def test_waiting_room_expires(self):
        room = create_room(self.host, now=self.now)
        room.created_at = self.now - timedelta(minutes=16)
        room.save(update_fields=['created_at'])
        state = state_for(self.host, now=self.now)
        self.assertIsNone(state['room'])
        self.assertEqual(GomokuRoom.objects.get(pk=room.pk).status, GomokuRoom.STATUS_CLOSED)
        with self.assertRaises(GomokuError):
            join_room(self.guest, room.code, now=self.now)


class GomokuPageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='caro_page', password='test')
        self.client = Client(HTTP_HOST='testserver')
        self.client.force_login(self.user)

    def test_page_and_create_room(self):
        page = self.client.get(reverse('utilities:gomoku'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Caro')
        self.assertContains(page, 'gomoku-boot')
        created = self.client.post(
            reverse('utilities:gomoku_create'),
            data=json.dumps({}),
            content_type='application/json',
        )
        self.assertEqual(created.status_code, 200)
        payload = created.json()
        self.assertTrue(payload['ok'])
        self.assertEqual(len(payload['room']['code']), 4)
        self.assertEqual(payload['room']['status'], 'waiting')
