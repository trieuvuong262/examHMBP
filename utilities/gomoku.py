"""Caro online: phòng mã 4 số, lượt 60 giây, Elo K=32.

Bàn 15×15, năm quân liên tiếp là thắng (sáu quân vẫn thắng). Không cấm nước.
Ván đầu chủ phòng cầm đen. Chơi lại thì đổi màu.
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.utils import timezone

from utilities.models import GomokuGame, GomokuRoom, GomokuStats, gomoku_empty_board

BOARD_SIZE = 15
WIN_LENGTH = 5
TURN_SECONDS = 60
WAITING_SECONDS = 15 * 60
ELO_START = 1000
ELO_K = 32
STONE_BLACK = 1
STONE_WHITE = 2
_DIRECTIONS = ((1, 0), (0, 1), (1, 1), (1, -1))

OPEN_STATUSES = GomokuRoom.OPEN_STATUSES


class GomokuError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def display_name(user) -> str:
    profile = getattr(user, 'profile', None)
    if profile is None:
        try:
            profile = user.profile
        except Exception:
            profile = None
    name = (getattr(profile, 'full_name', '') or '').strip()
    return name or user.get_username()


def opposite_color(color: str) -> str:
    if color == GomokuRoom.COLOR_BLACK:
        return GomokuRoom.COLOR_WHITE
    return GomokuRoom.COLOR_BLACK


def stone_for(color: str) -> int:
    return STONE_BLACK if color == GomokuRoom.COLOR_BLACK else STONE_WHITE


def color_for_stone(stone: int) -> str:
    return GomokuRoom.COLOR_BLACK if stone == STONE_BLACK else GomokuRoom.COLOR_WHITE


def has_five(board, row: int, col: int) -> bool:
    """Quân vừa đánh tạo ít nhất một dãy 5 liên tiếp."""
    stone = board[row][col]
    if stone not in (STONE_BLACK, STONE_WHITE):
        return False
    size = len(board)
    for dr, dc in _DIRECTIONS:
        count = 1
        for sign in (1, -1):
            r = row + dr * sign
            c = col + dc * sign
            while 0 <= r < size and 0 <= c < len(board[r]) and board[r][c] == stone:
                count += 1
                r += dr * sign
                c += dc * sign
        if count >= WIN_LENGTH:
            return True
    return False


def board_full(board) -> bool:
    return all(cell != 0 for row in board for cell in row)


def elo_change(player_elo: int, opponent_elo: int, score: float) -> int:
    """score: 1 thắng, 0.5 hòa, 0 thua."""
    expected = 1 / (1 + 10 ** ((opponent_elo - player_elo) / 400))
    return int(round(ELO_K * (score - expected)))


def user_color(room: GomokuRoom, user) -> str | None:
    if user.pk == room.host_id:
        return room.host_color
    if room.guest_id and user.pk == room.guest_id:
        return opposite_color(room.host_color)
    return None


def user_for_color(room: GomokuRoom, color: str):
    if room.host_color == color:
        return room.host
    return room.guest


def _now(now):
    return now or timezone.now()


def _lock_user(user):
    from django.contrib.auth import get_user_model

    get_user_model().objects.select_for_update().get(pk=user.pk)


def _locked_room(pk: int) -> GomokuRoom:
    return (
        GomokuRoom.objects.select_for_update(of=('self',))
        .select_related('host__profile', 'guest__profile', 'draw_offer_by')
        .get(pk=pk)
    )


def _open_rooms(user):
    return GomokuRoom.objects.filter(
        Q(host=user) | Q(guest=user),
        status__in=OPEN_STATUSES,
    )


def open_room_for(user) -> GomokuRoom | None:
    return (
        _open_rooms(user)
        .select_related('host__profile', 'guest__profile', 'draw_offer_by')
        .order_by('-id')
        .first()
    )


def expire_waiting_rooms(now=None) -> int:
    now = _now(now)
    cutoff = now - timedelta(seconds=WAITING_SECONDS)
    return GomokuRoom.objects.filter(
        status=GomokuRoom.STATUS_WAITING,
        created_at__lte=cutoff,
    ).update(status=GomokuRoom.STATUS_CLOSED, closed_at=now, updated_at=now)


def _copy_board(board) -> list:
    return [list(row) for row in board]


def _begin_round(room: GomokuRoom, *, swap: bool, now) -> None:
    if swap:
        room.host_color = opposite_color(room.host_color)
    room.board = gomoku_empty_board()
    room.turn = GomokuRoom.COLOR_BLACK
    room.move_count = 0
    room.last_row = None
    room.last_col = None
    room.status = GomokuRoom.STATUS_PLAYING
    room.turn_deadline = now + timedelta(seconds=TURN_SECONDS)
    room.draw_offer_by = None
    room.host_rematch = False
    room.guest_rematch = False


def _ensure_player(room: GomokuRoom, user) -> str:
    color = user_color(room, user)
    if color is None:
        raise GomokuError('Bạn không ở trong phòng này.')
    return color


def _lock_stats(user_ids: list[int]) -> dict[int, GomokuStats]:
    for uid in sorted(set(user_ids)):
        GomokuStats.objects.get_or_create(user_id=uid, defaults={'elo': ELO_START})
    locked = (
        GomokuStats.objects.select_for_update()
        .filter(user_id__in=user_ids)
        .order_by('user_id')
    )
    return {row.user_id: row for row in locked}


def _finish(room: GomokuRoom, *, result: str, reason: str, now) -> GomokuGame:
    if room.guest_id is None:
        raise GomokuError('Phòng chưa đủ hai người.')
    black = user_for_color(room, GomokuRoom.COLOR_BLACK)
    white = user_for_color(room, GomokuRoom.COLOR_WHITE)
    stats = _lock_stats([black.pk, white.pk])
    black_stats = stats[black.pk]
    white_stats = stats[white.pk]
    if result == GomokuGame.RESULT_DRAW:
        score_black = 0.5
        black_stats.draws += 1
        white_stats.draws += 1
    elif result == GomokuGame.RESULT_BLACK:
        score_black = 1.0
        black_stats.wins += 1
        white_stats.losses += 1
    else:
        score_black = 0.0
        white_stats.wins += 1
        black_stats.losses += 1
    black_before = black_stats.elo
    white_before = white_stats.elo
    black_stats.elo = max(0, black_before + elo_change(black_before, white_before, score_black))
    white_stats.elo = max(0, white_before + elo_change(white_before, black_before, 1 - score_black))
    black_stats.save(update_fields=['wins', 'losses', 'draws', 'elo', 'updated_at'])
    white_stats.save(update_fields=['wins', 'losses', 'draws', 'elo', 'updated_at'])
    game = GomokuGame.objects.create(
        room=room,
        black=black,
        white=white,
        result=result,
        reason=reason,
        black_elo_before=black_before,
        black_elo_after=black_stats.elo,
        white_elo_before=white_before,
        white_elo_after=white_stats.elo,
    )
    room.status = GomokuRoom.STATUS_FINISHED
    room.turn_deadline = None
    room.draw_offer_by = None
    room.host_rematch = False
    room.guest_rematch = False
    room.save()
    return game


def _apply_clock(room: GomokuRoom, now) -> bool:
    """Đóng phòng chờ quá hạn hoặc xử thua khi hết giờ lượt. Trả về True nếu đổi trạng thái."""
    if (
        room.status == GomokuRoom.STATUS_WAITING
        and room.created_at <= now - timedelta(seconds=WAITING_SECONDS)
    ):
        room.status = GomokuRoom.STATUS_CLOSED
        room.closed_at = now
        room.save(update_fields=['status', 'closed_at', 'updated_at'])
        return True
    if (
        room.status == GomokuRoom.STATUS_PLAYING
        and room.turn_deadline
        and room.turn_deadline <= now
    ):
        winner = opposite_color(room.turn)
        _finish(room, result=winner, reason=GomokuGame.REASON_TIMEOUT, now=now)
        return True
    return False


def sync_room(room: GomokuRoom, now=None) -> GomokuRoom:
    now = _now(now)
    with transaction.atomic():
        locked = _locked_room(room.pk)
        _apply_clock(locked, now)
        return locked


def _require_open(user) -> GomokuRoom:
    room = open_room_for(user)
    if room is None:
        raise GomokuError('Bạn không ở trong phòng nào.')
    return room


def _mutate(user, fn, now=None):
    now = _now(now)
    with transaction.atomic():
        _lock_user(user)
        return fn(now)


def create_room(user, now=None) -> GomokuRoom:
    def _create(now):
        if _open_rooms(user).exists():
            raise GomokuError('Bạn đang ở một phòng. Hãy rời phòng trước khi tạo phòng mới.')
        expire_waiting_rooms(now)
        for _ in range(30):
            code = f'{secrets.randbelow(10000):04d}'
            try:
                with transaction.atomic():
                    return GomokuRoom.objects.create(code=code, host=user)
            except IntegrityError:
                continue
        raise GomokuError('Không tạo được mã phòng. Thử lại.')

    return _mutate(user, _create, now)


def join_room(user, code: str, now=None) -> GomokuRoom:
    digits = ''.join(ch for ch in str(code or '') if ch.isdigit())
    if len(digits) != 4:
        raise GomokuError('Mã phòng phải gồm 4 số.')

    def _join(now):
        if _open_rooms(user).exists():
            raise GomokuError('Bạn đang ở một phòng. Hãy rời phòng trước khi vào phòng khác.')
        expire_waiting_rooms(now)
        room = (
            GomokuRoom.objects.select_for_update(of=('self',))
            .select_related('host__profile', 'guest__profile')
            .filter(code=digits, status__in=OPEN_STATUSES)
            .order_by('-id')
            .first()
        )
        if room is None:
            raise GomokuError('Không tìm thấy phòng này.')
        if room.host_id == user.pk:
            raise GomokuError('Đây là phòng của bạn.')
        _apply_clock(room, now)
        if room.status == GomokuRoom.STATUS_CLOSED:
            raise GomokuError('Phòng đã hết hạn.')
        if room.status != GomokuRoom.STATUS_WAITING or room.guest_id:
            raise GomokuError('Phòng không còn chờ người.')
        room.guest = user
        _begin_round(room, swap=False, now=now)
        room.save()
        return room

    return _mutate(user, _join, now)


def place_move(user, row: int, col: int, now=None) -> GomokuRoom:
    def _move(now):
        room = _locked_room(_require_open(user).pk)
        if _apply_clock(room, now):
            return room
        if room.status != GomokuRoom.STATUS_PLAYING:
            raise GomokuError('Ván chưa diễn ra.')
        color = _ensure_player(room, user)
        if color != room.turn:
            raise GomokuError('Chưa đến lượt bạn.')
        if isinstance(row, bool) or isinstance(col, bool) or not isinstance(row, int) or not isinstance(col, int):
            raise GomokuError('Ô đánh không hợp lệ.')
        if not (0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE):
            raise GomokuError('Ô đánh nằm ngoài bàn.')
        board = _copy_board(room.board)
        if len(board) != BOARD_SIZE or any(len(line) != BOARD_SIZE for line in board):
            raise GomokuError('Bàn cờ không hợp lệ.')
        if board[row][col] != 0:
            raise GomokuError('Ô này đã có quân.')
        board[row][col] = stone_for(color)
        room.board = board
        room.last_row = row
        room.last_col = col
        room.move_count += 1
        room.draw_offer_by = None
        if has_five(board, row, col):
            _finish(room, result=color, reason=GomokuGame.REASON_FIVE, now=now)
            return room
        if board_full(board):
            _finish(room, result=GomokuGame.RESULT_DRAW, reason=GomokuGame.REASON_DRAW, now=now)
            return room
        room.turn = opposite_color(color)
        room.turn_deadline = now + timedelta(seconds=TURN_SECONDS)
        room.save()
        return room

    return _mutate(user, _move, now)


def resign(user, now=None) -> GomokuRoom:
    def _resign(now):
        room = _locked_room(_require_open(user).pk)
        if _apply_clock(room, now):
            return room
        if room.status != GomokuRoom.STATUS_PLAYING:
            raise GomokuError('Không có ván để đầu hàng.')
        color = _ensure_player(room, user)
        _finish(room, result=opposite_color(color), reason=GomokuGame.REASON_RESIGN, now=now)
        return room

    return _mutate(user, _resign, now)


def offer_draw(user, now=None) -> GomokuRoom:
    def _offer(now):
        room = _locked_room(_require_open(user).pk)
        if _apply_clock(room, now):
            return room
        if room.status != GomokuRoom.STATUS_PLAYING:
            raise GomokuError('Không có ván để xin hòa.')
        _ensure_player(room, user)
        if room.draw_offer_by_id == user.pk:
            raise GomokuError('Bạn đã xin hòa.')
        if room.draw_offer_by_id:
            raise GomokuError('Đối thủ đã xin hòa. Hãy đồng ý hoặc từ chối.')
        room.draw_offer_by = user
        room.save(update_fields=['draw_offer_by', 'updated_at'])
        return room

    return _mutate(user, _offer, now)


def respond_draw(user, accept: bool, now=None) -> GomokuRoom:
    def _respond(now):
        room = _locked_room(_require_open(user).pk)
        if _apply_clock(room, now):
            return room
        if room.status != GomokuRoom.STATUS_PLAYING:
            raise GomokuError('Không có lời xin hòa.')
        _ensure_player(room, user)
        if not room.draw_offer_by_id:
            raise GomokuError('Chưa có lời xin hòa.')
        if room.draw_offer_by_id == user.pk:
            raise GomokuError('Đối thủ chưa trả lời lời xin hòa của bạn.')
        if not accept:
            room.draw_offer_by = None
            room.save(update_fields=['draw_offer_by', 'updated_at'])
            return room
        _finish(room, result=GomokuGame.RESULT_DRAW, reason=GomokuGame.REASON_DRAW, now=now)
        return room

    return _mutate(user, _respond, now)


def request_rematch(user, now=None) -> GomokuRoom:
    def _rematch(now):
        room = _locked_room(_require_open(user).pk)
        _apply_clock(room, now)
        if room.status != GomokuRoom.STATUS_FINISHED:
            raise GomokuError('Ván chưa kết thúc.')
        _ensure_player(room, user)
        if user.pk == room.host_id:
            room.host_rematch = True
        else:
            room.guest_rematch = True
        if room.host_rematch and room.guest_rematch:
            _begin_round(room, swap=True, now=now)
        room.save()
        return room

    return _mutate(user, _rematch, now)


def leave_room(user, now=None) -> None:
    def _leave(now):
        room = _locked_room(_require_open(user).pk)
        _apply_clock(room, now)
        if room.status == GomokuRoom.STATUS_CLOSED:
            return None
        if room.status == GomokuRoom.STATUS_PLAYING:
            raise GomokuError('Ván đang chơi. Hãy đầu hàng nếu muốn kết thúc.')
        room.status = GomokuRoom.STATUS_CLOSED
        room.closed_at = now
        room.save(update_fields=['status', 'closed_at', 'updated_at'])
        return None

    return _mutate(user, _leave, now)


def stats_for(user) -> dict:
    stats, _ = GomokuStats.objects.get_or_create(user=user, defaults={'elo': ELO_START})
    return {
        'elo': stats.elo,
        'wins': stats.wins,
        'losses': stats.losses,
        'draws': stats.draws,
        'played': stats.wins + stats.losses + stats.draws,
    }


def leaderboard(user, limit: int = 50) -> list[dict]:
    rows = (
        GomokuStats.objects.annotate(played=F('wins') + F('losses') + F('draws'))
        .filter(played__gt=0)
        .select_related('user__profile')
        .order_by('-elo', '-wins', 'losses', 'user__profile__full_name', 'user__username')[:limit]
    )
    result = []
    for index, row in enumerate(rows, start=1):
        result.append({
            'rank': index,
            'name': display_name(row.user),
            'elo': row.elo,
            'wins': row.wins,
            'losses': row.losses,
            'draws': row.draws,
            'is_me': row.user_id == user.pk,
        })
    return result


def _reason_label(reason: str) -> str:
    return {
        GomokuGame.REASON_FIVE: 'Năm quân liên tiếp',
        GomokuGame.REASON_RESIGN: 'Đầu hàng',
        GomokuGame.REASON_TIMEOUT: 'Hết giờ',
        GomokuGame.REASON_DRAW: 'Hòa',
    }.get(reason, reason)


def _outcome_for(game: GomokuGame, user) -> tuple[str, int, int]:
    if user.pk == game.black_id:
        before, after = game.black_elo_before, game.black_elo_after
        if game.result == GomokuGame.RESULT_DRAW:
            return 'draw', before, after
        if game.result == GomokuGame.RESULT_BLACK:
            return 'win', before, after
        return 'loss', before, after
    before, after = game.white_elo_before, game.white_elo_after
    if game.result == GomokuGame.RESULT_DRAW:
        return 'draw', before, after
    if game.result == GomokuGame.RESULT_WHITE:
        return 'win', before, after
    return 'loss', before, after


def history_for(user, limit: int = 30) -> list[dict]:
    games = (
        GomokuGame.objects.filter(Q(black=user) | Q(white=user))
        .select_related('black__profile', 'white__profile')
        .order_by('-finished_at', '-id')[:limit]
    )
    rows = []
    labels = {'win': 'Thắng', 'loss': 'Thua', 'draw': 'Hòa'}
    for game in games:
        opponent = game.white if user.pk == game.black_id else game.black
        outcome, before, after = _outcome_for(game, user)
        rows.append({
            'played_at': game.finished_at,
            'opponent': display_name(opponent),
            'outcome': outcome,
            'outcome_label': labels[outcome],
            'reason_label': _reason_label(game.reason),
            'elo_before': before,
            'elo_after': after,
            'elo_delta': after - before,
        })
    return rows


def _seconds_left(deadline, now) -> int | None:
    if deadline is None:
        return None
    return max(0, int((deadline - now).total_seconds()))


def room_payload(room: GomokuRoom | None, user, now=None) -> dict | None:
    if room is None or room.status == GomokuRoom.STATUS_CLOSED:
        return None
    now = _now(now)
    color = user_color(room, user)
    opponent = None
    if room.guest_id:
        opponent = room.guest if user.pk == room.host_id else room.host
    you_rematch = room.host_rematch if user.pk == room.host_id else room.guest_rematch
    opponent_rematch = room.guest_rematch if user.pk == room.host_id else room.host_rematch
    if room.draw_offer_by_id == user.pk:
        draw_offer = 'you'
    elif room.draw_offer_by_id:
        draw_offer = 'opponent'
    else:
        draw_offer = 'none'
    result = None
    if room.status == GomokuRoom.STATUS_FINISHED:
        game = room.games.select_related('black__profile', 'white__profile').order_by('-id').first()
        if game is not None:
            outcome, before, after = _outcome_for(game, user)
            result = {
                'game_id': game.id,
                'outcome': outcome,
                'outcome_label': {'win': 'Bạn thắng', 'loss': 'Bạn thua', 'draw': 'Hòa'}[outcome],
                'reason': game.reason,
                'reason_label': _reason_label(game.reason),
                'elo_before': before,
                'elo_after': after,
                'elo_delta': after - before,
            }
    waiting_left = None
    if room.status == GomokuRoom.STATUS_WAITING:
        waiting_left = _seconds_left(room.created_at + timedelta(seconds=WAITING_SECONDS), now)
    return {
        'code': room.code,
        'status': room.status,
        'board': room.board,
        'your_color': color,
        'turn': room.turn,
        'your_turn': room.status == GomokuRoom.STATUS_PLAYING and color == room.turn,
        'your_name': display_name(user),
        'opponent_name': display_name(opponent) if opponent else None,
        'seconds_left': _seconds_left(room.turn_deadline, now) if room.status == GomokuRoom.STATUS_PLAYING else None,
        'turn_deadline': room.turn_deadline,
        'waiting_seconds_left': waiting_left,
        'draw_offer': draw_offer,
        'you_rematch': you_rematch,
        'opponent_rematch': opponent_rematch,
        'move_count': room.move_count,
        'last_move': [room.last_row, room.last_col] if room.last_row is not None else None,
        'result': result,
        'server_now': now,
    }


def state_for(user, now=None) -> dict:
    now = _now(now)
    room = open_room_for(user)
    if room is not None:
        room = sync_room(room, now)
    return {
        'room': room_payload(room, user, now),
        'me': stats_for(user),
        'server_now': now,
    }


def lists_for(user) -> dict:
    return {
        'me': stats_for(user),
        'leaderboard': leaderboard(user),
        'history': history_for(user),
    }
