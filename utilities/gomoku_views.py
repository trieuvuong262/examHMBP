import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from assessment.decorators import module_perm_required
from hrm.module_permissions import MODULE_UTILITIES

from utilities.gomoku import (
    GomokuError,
    create_room,
    history_for,
    join_room,
    leaderboard,
    leave_room,
    lists_for,
    offer_draw,
    place_move,
    request_rematch,
    resign,
    respond_draw,
    state_for,
    stats_for,
)


def _body(request) -> dict:
    if not request.body:
        return {}
    try:
        data = json.loads(request.body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GomokuError('Dữ liệu không hợp lệ.')
    if not isinstance(data, dict):
        raise GomokuError('Dữ liệu không hợp lệ.')
    return data


def _json_error(message: str, status: int = 400):
    return JsonResponse({'ok': False, 'message': message}, status=status)


def _act(request, fn):
    try:
        data = _body(request)
        fn(request.user, data)
    except GomokuError as exc:
        return _json_error(exc.message)
    payload = state_for(request.user)
    payload['ok'] = True
    return JsonResponse(payload)


@login_required
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_home(request):
    state = state_for(request.user)
    boot = {
        'room': state['room'],
        'me': state['me'],
        'serverNow': state['server_now'],
        'leaderboard': leaderboard(request.user),
        'history': history_for(request.user),
        'urls': {
            'state': reverse('utilities:gomoku_state'),
            'lists': reverse('utilities:gomoku_lists'),
            'create': reverse('utilities:gomoku_create'),
            'join': reverse('utilities:gomoku_join'),
            'move': reverse('utilities:gomoku_move'),
            'resign': reverse('utilities:gomoku_resign'),
            'draw': reverse('utilities:gomoku_draw'),
            'rematch': reverse('utilities:gomoku_rematch'),
            'leave': reverse('utilities:gomoku_leave'),
        },
    }
    return render(request, 'utilities/gomoku.html', {'boot': boot, 'me': stats_for(request.user)})


@login_required
@require_GET
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_state(request):
    payload = state_for(request.user)
    payload['ok'] = True
    return JsonResponse(payload)


@login_required
@require_GET
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_lists(request):
    payload = lists_for(request.user)
    payload['ok'] = True
    return JsonResponse(payload)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_create(request):
    def _run(user, _data):
        create_room(user)

    return _act(request, _run)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_join(request):
    def _run(user, data):
        join_room(user, data.get('code', ''))

    return _act(request, _run)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_move(request):
    def _run(user, data):
        place_move(user, data.get('row'), data.get('col'))

    return _act(request, _run)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_resign(request):
    def _run(user, _data):
        resign(user)

    return _act(request, _run)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_draw(request):
    def _run(user, data):
        action = data.get('action')
        if action == 'offer':
            offer_draw(user)
        elif action == 'accept':
            respond_draw(user, True)
        elif action == 'decline':
            respond_draw(user, False)
        else:
            raise GomokuError('Thao tác hòa không hợp lệ.')

    return _act(request, _run)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_rematch(request):
    def _run(user, _data):
        request_rematch(user)

    return _act(request, _run)


@login_required
@require_POST
@module_perm_required(MODULE_UTILITIES, 'view')
def gomoku_leave(request):
    def _run(user, _data):
        leave_room(user)

    return _act(request, _run)
