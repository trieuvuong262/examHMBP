(function () {
    var bootNode = document.getElementById('gomoku-boot');
    if (!bootNode) return;
    var boot = JSON.parse(bootNode.textContent);
    var csrfNode = document.querySelector('meta[name="csrf-token"]');
    var csrf = csrfNode ? csrfNode.getAttribute('content') : '';
    var SIZE = 15;
    var STARS = {
        '3,3': 1, '3,7': 1, '3,11': 1,
        '7,3': 1, '7,7': 1, '7,11': 1,
        '11,3': 1, '11,7': 1, '11,11': 1,
    };

    var room = boot.room || null;
    var skew = Date.now() - Date.parse(boot.serverNow);
    var pollTimer = null;
    var clockTimer = null;
    var acting = false;
    var polling = false;
    var boardKey = '';
    var playersKey = '';
    var bannerKey = '';
    var actionsKey = '';
    var chatKey = '';
    var deadlineArmed = false;
    var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function $(id) { return document.getElementById(id); }

    function showError(message) {
        var el = $('gomoku-toast');
        if (!message) {
            el.classList.add('d-none');
            el.textContent = '';
            return;
        }
        el.textContent = message;
        el.classList.remove('d-none');
    }

    function readPayload(response) {
        return response.text().then(function (text) {
            var data = null;
            try { data = JSON.parse(text); } catch (e) { data = null; }
            if (!data || typeof data !== 'object') {
                throw new Error('Phiên đăng nhập đã hết. Tải lại trang.');
            }
            if (!response.ok || data.ok === false) {
                throw new Error(data.message || 'Không thực hiện được.');
            }
            return data;
        });
    }

    function post(url, data) {
        return fetch(url, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': csrf,
            },
            body: JSON.stringify(data || {}),
        }).then(readPayload);
    }

    function get(url) {
        return fetch(url, {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' },
        }).then(readPayload);
    }

    function pad(n) {
        return n < 10 ? '0' + n : String(n);
    }

    function formatClock(seconds) {
        var s = Math.max(0, seconds);
        return Math.floor(s / 60) + ':' + pad(s % 60);
    }

    function formatWhen(iso) {
        var date = new Date(iso);
        if (Number.isNaN(date.getTime())) return '';
        return date.toLocaleString('vi-VN', {
            hour: '2-digit',
            minute: '2-digit',
            day: '2-digit',
            month: '2-digit',
            year: 'numeric',
        });
    }

    function deltaText(delta) {
        if (delta > 0) return '+' + delta;
        return String(delta);
    }

    function rememberWaiting(data) {
        if (data.server_now) skew = Date.now() - Date.parse(data.server_now);
        if (room && room.status === 'waiting' && room.waiting_seconds_left != null) {
            room._waitUntil = Date.parse(data.server_now) + room.waiting_seconds_left * 1000;
        }
    }

    function secondsLeft() {
        if (!room) return null;
        var now = Date.now() - skew;
        if (room.status === 'playing' && room.turn_deadline) {
            return Math.max(0, Math.ceil((Date.parse(room.turn_deadline) - now) / 1000));
        }
        if (room.status === 'waiting' && room._waitUntil) {
            return Math.max(0, Math.ceil((room._waitUntil - now) / 1000));
        }
        return null;
    }

    function renderMe(me) {
        if (!me) return;
        $('gomoku-my-elo').textContent = me.elo;
        $('gomoku-wins').textContent = me.wins;
        $('gomoku-losses').textContent = me.losses;
        $('gomoku-draws').textContent = me.draws;
    }

    function renderRanks(rows) {
        var body = $('gomoku-ranks');
        var empty = $('gomoku-ranks-empty');
        body.textContent = '';
        if (!rows || !rows.length) {
            empty.classList.remove('d-none');
            return;
        }
        empty.classList.add('d-none');
        rows.forEach(function (row) {
            var tr = document.createElement('tr');
            if (row.is_me) tr.className = 'is-me';
            var medal = row.rank <= 3
                ? '<span class="gomoku-medal is-' + row.rank + '">' + row.rank + '</span>'
                : String(row.rank);
            var avatar = row.avatar_url
                ? '<img class="gomoku-avatar" src="' + escapeHtml(row.avatar_url) + '" alt="">'
                : '<span class="gomoku-avatar is-fallback" aria-hidden="true">' + escapeHtml(row.initial || '?') + '</span>';
            tr.innerHTML =
                '<td>' + medal + '</td>' +
                '<td><span class="gomoku-person">' + avatar + '<span>' + escapeHtml(row.name) + '</span></span></td>' +
                '<td class="text-end fw-semibold">' + row.elo + '</td>' +
                '<td class="text-end">' + row.wins + '/' + row.draws + '/' + row.losses + '</td>';
            body.appendChild(tr);
        });
    }

    function renderHistory(rows) {
        var body = $('gomoku-history');
        var empty = $('gomoku-history-empty');
        body.textContent = '';
        if (!rows || !rows.length) {
            empty.classList.remove('d-none');
            return;
        }
        empty.classList.add('d-none');
        rows.forEach(function (row) {
            var tr = document.createElement('tr');
            var tone = row.outcome === 'win' ? 'text-success' : (row.outcome === 'loss' ? 'text-danger' : 'text-muted');
            tr.innerHTML =
                '<td class="text-nowrap">' + escapeHtml(formatWhen(row.played_at)) + '</td>' +
                '<td>' + escapeHtml(row.opponent) + '</td>' +
                '<td><span class="gomoku-pill is-' + row.outcome + '">' + escapeHtml(row.outcome_label) + '</span>' +
                ' <span class="text-muted">' + escapeHtml(row.reason_label) + '</span></td>' +
                '<td class="text-end text-nowrap">' + row.elo_before + ' → ' + row.elo_after +
                ' <span class="' + tone + '">(' + deltaText(row.elo_delta) + ')</span></td>';
            body.appendChild(tr);
        });
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function button(label, className, onClick) {
        var btn = document.createElement('button');
        btn.type = 'button';
        btn.className = className;
        btn.textContent = label;
        btn.addEventListener('click', onClick);
        return btn;
    }

    function winningMarks(board, last) {
        var marks = {};
        if (!last || !board[last[0]]) return marks;
        var row = last[0];
        var col = last[1];
        var stone = board[row][col];
        if (!stone) return marks;
        var dirs = [[1, 0], [0, 1], [1, 1], [1, -1]];
        dirs.forEach(function (dir) {
            var cells = [[row, col]];
            [1, -1].forEach(function (sign) {
                var r = row + dir[0] * sign;
                var c = col + dir[1] * sign;
                while (r >= 0 && r < SIZE && c >= 0 && c < SIZE && board[r][c] === stone) {
                    cells.push([r, c]);
                    r += dir[0] * sign;
                    c += dir[1] * sign;
                }
            });
            if (cells.length >= 5) {
                cells.forEach(function (cell) {
                    marks[cell[0] + ',' + cell[1]] = 1;
                });
            }
        });
        return marks;
    }

    function renderBoard() {
        var showWin = room && room.status === 'finished' && room.result && room.result.reason === 'five';
        var key = JSON.stringify({
            board: room ? room.board : null,
            last: room ? room.last_move : null,
            turn: room ? room.your_turn : false,
            status: room ? room.status : '',
            color: room ? room.your_color : '',
            win: !!showWin,
        });
        if (key === boardKey) return;
        boardKey = key;
        var grid = $('gomoku-board');
        grid.textContent = '';
        if (!room) return;
        var wins = showWin ? winningMarks(room.board, room.last_move) : {};
        for (var r = 0; r < SIZE; r += 1) {
            for (var c = 0; c < SIZE; c += 1) {
                var cell = document.createElement('button');
                cell.type = 'button';
                cell.className = 'gomoku-cell';
                cell.setAttribute('role', 'gridcell');
                cell.setAttribute('aria-label', 'Hàng ' + (r + 1) + ' cột ' + (c + 1));
                if (r === 0) cell.classList.add('edge-top');
                if (r === SIZE - 1) cell.classList.add('edge-bottom');
                if (c === 0) cell.classList.add('edge-left');
                if (c === SIZE - 1) cell.classList.add('edge-right');
                if (wins[r + ',' + c]) cell.classList.add('win');
                if (STARS[r + ',' + c]) {
                    var star = document.createElement('span');
                    star.className = 'gomoku-star';
                    cell.appendChild(star);
                }
                var stone = room.board[r][c];
                var isLast = room.last_move && room.last_move[0] === r && room.last_move[1] === c;
                if (stone) {
                    var piece = document.createElement('span');
                    piece.className = 'gomoku-stone ' + (stone === 1 ? 'black' : 'white');
                    if (isLast) piece.classList.add('is-new');
                    cell.appendChild(piece);
                } else if (room.your_turn) {
                    cell.classList.add('can-play');
                    var ghost = document.createElement('span');
                    ghost.className = 'gomoku-ghost ' + room.your_color;
                    cell.appendChild(ghost);
                    cell.addEventListener('click', onCell(r, c));
                }
                if (isLast) cell.classList.add('last');
                grid.appendChild(cell);
            }
        }
    }

    function onCell(row, col) {
        return function () {
            if (acting || !room || !room.your_turn) return;
            act(boot.urls.move, { row: row, col: col });
        };
    }

    function renderPlayers() {}

    function renderBanner() {
        var banner = $('gomoku-banner');
        var text = '';
        var tone = '';
        if (room && room.status === 'playing' && room.undo_offer === 'you') {
            tone = 'is-info';
            text = 'Bạn đã xin đi lại. Đồng hồ lượt vẫn chạy.';
        } else if (room && room.status === 'playing' && room.undo_offer === 'opponent') {
            tone = 'is-info';
            text = 'Đối thủ xin đi lại. Đồng hồ lượt vẫn chạy.';
        } else if (room && room.status === 'playing' && room.draw_offer === 'you') {
            tone = 'is-info';
            text = 'Bạn đã xin hòa. Đồng hồ lượt vẫn chạy.';
        } else if (room && room.status === 'playing' && room.draw_offer === 'opponent') {
            tone = 'is-info';
            text = 'Đối thủ xin hòa. Đồng hồ lượt vẫn chạy.';
        }
        var key = tone + '|' + text;
        if (key === bannerKey) return;
        bannerKey = key;
        banner.className = 'gomoku-banner' + (tone ? ' ' + tone : '');
        if (!text) {
            banner.classList.add('d-none');
            banner.textContent = '';
            return;
        }
        banner.textContent = text;
    }

    var resultDismissed = '';

    function resultStamp() {
        if (!room || !room.result) return '';
        var result = room.result;
        return [result.game_id, result.outcome, result.reason_label, result.elo_before, result.elo_after].join('|');
    }

    function renderResult() {
        var box = $('gomoku-result');
        if (!box) return;
        if (!room || room.status !== 'finished' || !room.result) {
            box.hidden = true;
            resultDismissed = '';
            return;
        }
        var stamp = resultStamp();
        if (stamp === resultDismissed) {
            box.hidden = true;
            return;
        }
        var result = room.result;
        var titles = { win: 'Bạn đã thắng', loss: 'Bạn đã thua', draw: 'Ván hòa' };
        var marks = { win: '✓', loss: '✕', draw: '=' };
        box.hidden = false;
        box.className = 'gomoku-popup is-' + result.outcome;
        $('gomoku-popup-mark').textContent = marks[result.outcome] || '•';
        $('gomoku-popup-title').textContent = titles[result.outcome] || result.outcome_label;
        $('gomoku-popup-reason').textContent = result.reason_label;
        $('gomoku-popup-elo').textContent = result.elo_before + ' → ' + result.elo_after + '  (' + deltaText(result.elo_delta) + ' điểm)';
    }

    var askDismissed = '';
    var askShown = '';
    var resignOpen = false;

    function askKind() {
        if (!room) return '';
        if (room.status === 'playing' && room.undo_offer === 'opponent') return 'undo';
        if (room.status === 'playing' && room.draw_offer === 'opponent') return 'draw';
        if (room.status === 'finished' && room.opponent_rematch && !room.you_rematch) {
            return 'rematch:' + ((room.result && room.result.game_id) || '');
        }
        return '';
    }

    function drawAskNote() {
        var left = secondsLeft();
        return 'Đồng hồ lượt vẫn chạy.' + (left == null ? '' : ' Còn ' + formatClock(left) + '.');
    }

    function resultVisible() {
        var box = $('gomoku-result');
        return !!(box && !box.hidden);
    }

    function resignNote() {
        var left = secondsLeft();
        var clock = left == null ? '' : ' Còn ' + formatClock(left) + '.';
        return 'Bạn thua ngay.' + clock;
    }

    function fillAsk(kind) {
        var draw = kind === 'draw';
        var resign = kind === 'resign';
        var box = $('gomoku-ask');
        var yes = $('gomoku-ask-yes');
        var later = $('gomoku-ask-later');
        later.hidden = resign;
        yes.className = resign ? 'btn btn-danger' : 'btn btn-hm';
        if (resign) {
            box.className = 'gomoku-popup is-ask-resign';
            $('gomoku-ask-mark').textContent = '✕';
            $('gomoku-ask-kicker').textContent = 'Xác nhận';
            $('gomoku-ask-title').textContent = 'Đầu hàng ván này?';
            $('gomoku-ask-reason').textContent = resignNote();
            yes.textContent = 'Đầu hàng';
            $('gomoku-ask-no').textContent = 'Chơi tiếp';
            return;
        }
        if (kind === 'undo') {
            box.className = 'gomoku-popup is-ask-undo';
            $('gomoku-ask-mark').textContent = '↺';
            $('gomoku-ask-kicker').textContent = 'Đi lại';
            $('gomoku-ask-title').textContent = 'Đối thủ xin đi lại';
            $('gomoku-ask-reason').textContent = drawAskNote();
            yes.textContent = 'Đồng ý';
            $('gomoku-ask-no').textContent = 'Từ chối';
            later.textContent = 'Quay lại';
            return;
        }
        box.className = 'gomoku-popup ' + (draw ? 'is-ask-draw' : 'is-ask-rematch');
        $('gomoku-ask-mark').textContent = draw ? '=' : '↻';
        $('gomoku-ask-kicker').textContent = draw ? 'Xin hòa' : 'Chơi lại';
        $('gomoku-ask-title').textContent = draw ? 'Đối thủ xin hòa' : 'Đối thủ muốn chơi lại';
        $('gomoku-ask-reason').textContent = draw ? drawAskNote() : 'Ván mới đổi màu quân.';
        yes.textContent = draw ? 'Đồng ý hòa' : 'Chơi lại';
        $('gomoku-ask-no').textContent = draw ? 'Từ chối' : 'Rời phòng';
        later.textContent = draw ? 'Quay lại' : 'Để sau';
    }

    function renderAsk() {
        var box = $('gomoku-ask');
        if (!box) return;
        if (resignOpen && room && room.status === 'playing') {
            if (askShown !== 'resign') {
                askShown = 'resign';
                fillAsk('resign');
            }
            box.hidden = false;
            return;
        }
        resignOpen = false;
        var kind = askKind();
        if (!kind) {
            box.hidden = true;
            askDismissed = '';
            askShown = '';
            return;
        }
        if (askDismissed === kind || resultVisible()) {
            box.hidden = true;
            return;
        }
        if (askShown !== kind) {
            askShown = kind;
            fillAsk(kind);
        }
        box.hidden = false;
    }

    function dismissAsk() {
        if (resignOpen) {
            resignOpen = false;
            askShown = '';
            renderAsk();
            return;
        }
        askDismissed = askKind();
        var box = $('gomoku-ask');
        if (box) box.hidden = true;
    }

    function answerAsk(accept) {
        if (!room || acting) return;
        if (resignOpen) {
            resignOpen = false;
            askShown = '';
            if (!accept) {
                renderAsk();
                return;
            }
            var askBox = $('gomoku-ask');
            if (askBox) askBox.hidden = true;
            act(boot.urls.resign, {});
            return;
        }
        if (room.status === 'playing' && room.undo_offer === 'opponent') {
            act(boot.urls.undo, { action: accept ? 'accept' : 'decline' });
            return;
        }
        if (room.status === 'playing' && room.draw_offer === 'opponent') {
            act(boot.urls.draw, { action: accept ? 'accept' : 'decline' });
            return;
        }
        if (room.status === 'finished' && room.opponent_rematch && !room.you_rematch) {
            if (accept) act(boot.urls.rematch, {});
            else act(boot.urls.leave, {}, { silentClose: true });
        }
    }

    function celebrate(outcome) {
        var box = $('gomoku-confetti');
        if (!box || outcome !== 'win' || reducedMotion) return;
        box.textContent = '';
        var colors = ['#dc2626', '#111111', '#f8fafc', '#e8c48a', '#f5c451'];
        for (var i = 0; i < 16; i += 1) {
            var piece = document.createElement('i');
            piece.style.setProperty('--x', (Math.random() * 180 - 90) + 'px');
            piece.style.setProperty('--r', (Math.random() * 240 - 120) + 'deg');
            piece.style.setProperty('--d', (0.55 + Math.random() * 0.35) + 's');
            piece.style.background = colors[i % colors.length];
            box.appendChild(piece);
        }
    }

    function renderActions() {
        var key = [room.status, room.draw_offer, room.undo_offer, room.move_count, room.you_rematch, room.opponent_rematch].join('|');
        if (key === actionsKey) return;
        actionsKey = key;
        var box = $('gomoku-actions');
        box.className = 'gomoku-actions';
        box.textContent = '';
        if (!room) return;
        if (room.status === 'waiting') {
            box.appendChild(button('Hủy phòng', 'btn btn-outline-danger', function () {
                act(boot.urls.leave, {}, { silentClose: true });
            }));
            return;
        }
        if (room.status === 'playing') {
            var row = document.createElement('div');
            row.className = 'gomoku-actions-row';
            var resign = button('Đầu hàng', 'btn btn-outline-danger', function () {
                resignOpen = true;
                askShown = '';
                renderAsk();
            });
            var undo = button(room.undo_offer === 'you' ? 'Đang chờ' : 'Đi lại', 'btn btn-outline-secondary', function () {
                act(boot.urls.undo, { action: 'offer' });
            });
            undo.disabled = room.undo_offer === 'you' || !room.move_count;
            if (room.undo_offer === 'opponent') {
                row.appendChild(button('Đồng ý', 'btn btn-hm', function () {
                    act(boot.urls.undo, { action: 'accept' });
                }));
                row.appendChild(button('Từ chối', 'btn btn-outline-secondary', function () {
                    act(boot.urls.undo, { action: 'decline' });
                }));
                row.appendChild(resign);
            } else if (room.undo_offer === 'you' || room.draw_offer === 'you') {
                if (room.undo_offer === 'you') row.appendChild(undo);
                row.appendChild(resign);
            } else if (room.draw_offer === 'opponent') {
                row.appendChild(button('Đồng ý hòa', 'btn btn-hm', function () {
                    act(boot.urls.draw, { action: 'accept' });
                }));
                row.appendChild(button('Từ chối', 'btn btn-outline-secondary', function () {
                    act(boot.urls.draw, { action: 'decline' });
                }));
                row.appendChild(resign);
            } else {
                row.appendChild(undo);
                row.appendChild(button('Xin hòa', 'btn btn-outline-secondary', function () {
                    act(boot.urls.draw, { action: 'offer' });
                }));
                row.appendChild(resign);
            }
            box.appendChild(row);
            return;
        }
        if (room.status === 'finished') {
            var done = document.createElement('div');
            done.className = 'gomoku-actions-row';
            var again = button(room.you_rematch ? 'Đang chờ đối thủ' : 'Chơi lại', 'btn btn-hm', function () {
                act(boot.urls.rematch, {});
            });
            again.disabled = room.you_rematch;
            done.appendChild(again);
            done.appendChild(button('Rời phòng', 'btn btn-outline-secondary', function () {
                act(boot.urls.leave, {}, { silentClose: true });
            }));
            box.appendChild(done);
        }
    }

    function paintClock(seconds, total, lowAt) {
        var clock = $('gomoku-clock');
        var ring = $('gomoku-clock-ring');
        var ratio = seconds == null || !total ? 0 : Math.max(0, Math.min(1, seconds / total));
        if (ring) ring.style.setProperty('--p', String(ratio));
        clock.textContent = seconds == null ? '—' : formatClock(seconds);
        var low = seconds != null && seconds <= lowAt;
        if (ring) ring.classList.toggle('is-low', low);
        clock.classList.toggle('is-low', low);
    }

    function renderClock() {
        var label = $('gomoku-turn-label');
        if (!room) return;
        if (room.status === 'waiting') {
            label.textContent = 'Đang chờ người vào';
            paintClock(secondsLeft(), 15 * 60, 60);
            return;
        }
        if (room.status === 'playing') {
            label.textContent = room.your_turn
                ? 'Lượt của bạn'
                : ('Lượt của: ' + (room.opponent_name || 'đối thủ'));
            var turnLeft = secondsLeft();
            paintClock(turnLeft, 60, 10);
            if (turnLeft === 0) {
                if (!deadlineArmed) {
                    deadlineArmed = true;
                    pollSoon();
                }
            } else {
                deadlineArmed = false;
            }
            var askReason = $('gomoku-ask-reason');
            var ask = $('gomoku-ask');
            var askKindNow = askKind();
            if (askReason && ask && !ask.hidden && (resignOpen || askKindNow === 'draw' || askKindNow === 'undo')) {
                askReason.textContent = resignOpen ? resignNote() : drawAskNote();
            }
            return;
        }
        label.textContent = 'Ván đã kết thúc';
        paintClock(null, 60, 10);
    }

    function renderCode() {
        var box = $('gomoku-room-code');
        if (box.dataset.code === room.code) return;
        box.dataset.code = room.code;
        box.textContent = '';
        room.code.split('').forEach(function (digit) {
            var cell = document.createElement('span');
            cell.textContent = digit;
            box.appendChild(cell);
        });
    }

    function nativeFullscreenElement() {
        return document.fullscreenElement || document.webkitFullscreenElement || null;
    }

    var expandNative = false;

    function setExpanded(on) {
        var page = document.querySelector('.gomoku-page');
        if (page) page.classList.toggle('is-expanded', on);
        var expandBtn = $('gomoku-expand');
        if (!expandBtn) return;
        expandBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
        expandBtn.setAttribute('aria-label', on ? 'Thu nhỏ' : 'Phóng to màn hình');
        expandBtn.title = on ? 'Thu nhỏ' : 'Phóng to';
    }

    function collapsePlay() {
        var page = document.querySelector('.gomoku-page');
        var expanded = page && page.classList.contains('is-expanded');
        var native = nativeFullscreenElement();
        if (!expanded && !native) return;
        expandNative = false;
        setExpanded(false);
        var exit = document.exitFullscreen || document.webkitExitFullscreen;
        if (native && exit) {
            var pending = exit.call(document);
            if (pending && pending.catch) pending.catch(function () {});
        }
    }

    function toggleExpand() {
        var page = document.querySelector('.gomoku-page');
        var stage = $('gomoku-stage');
        var on = (page && page.classList.contains('is-expanded')) || nativeFullscreenElement();
        if (on) {
            collapsePlay();
            return;
        }
        setExpanded(true);
        var req = stage && (stage.requestFullscreen || stage.webkitRequestFullscreen);
        if (!req) return;
        try {
            var pending = req.call(stage);
            if (pending && pending.then) {
                pending.then(function () {
                    expandNative = true;
                }).catch(function () {
                    expandNative = false;
                });
            } else {
                expandNative = !!nativeFullscreenElement();
            }
        } catch (err) {
            expandNative = false;
        }
    }

    function renderChat() {
        var box = $('gomoku-chat');
        if (!box) return;
        var open = room && room.opponent_name && (room.status === 'playing' || room.status === 'finished');
        box.hidden = !open;
        if (!open) {
            chatKey = '';
            return;
        }
        var messages = room.messages || [];
        var key = messages.map(function (msg) { return msg.id; }).join(',');
        if (key === chatKey) return;
        var log = $('gomoku-chat-log');
        var stick = !chatKey || log.scrollHeight - log.scrollTop - log.clientHeight < 48;
        log.textContent = '';
        if (!messages.length) {
            var empty = document.createElement('p');
            empty.className = 'gomoku-chat-empty';
            empty.textContent = 'Nhắn cho đối thủ.';
            log.appendChild(empty);
        }
        messages.forEach(function (msg) {
            var item = document.createElement('div');
            item.className = 'gomoku-chat-msg' + (msg.mine ? ' is-mine' : '');
            var name = document.createElement('strong');
            name.textContent = msg.mine ? 'Bạn' : (msg.name || 'Đối thủ');
            var body = document.createElement('span');
            body.textContent = msg.body;
            item.appendChild(name);
            item.appendChild(body);
            log.appendChild(item);
        });
        if (stick) log.scrollTop = log.scrollHeight;
        chatKey = key;
    }

    function render() {
        var inRoom = !!room;
        var page = document.querySelector('.gomoku-page');
        if (page) page.classList.toggle('is-match', inRoom);
        $('gomoku-lobby').classList.toggle('d-none', inRoom);
        $('gomoku-match').classList.toggle('d-none', !inRoom);
        var pageHead = $('gomoku-page-head');
        if (pageHead) pageHead.classList.toggle('d-none', inRoom);
        var roomCard = $('gomoku-room-card');
        if (roomCard) roomCard.classList.toggle('d-none', !inRoom);
        if (!inRoom) {
            boardKey = '';
            playersKey = '';
            bannerKey = '';
            actionsKey = '';
            var frameIdle = $('gomoku-frame');
            if (frameIdle) frameIdle.classList.remove('is-your-turn');
            collapsePlay();
            var askBox = $('gomoku-ask');
            if (askBox) askBox.hidden = true;
            var resultBox = $('gomoku-result');
            if (resultBox) resultBox.hidden = true;
            askDismissed = '';
            askShown = '';
            resignOpen = false;
            resultDismissed = '';
            chatKey = '';
            schedulePoll();
            return;
        }
        renderCode();
        var frame = $('gomoku-frame');
        if (frame) frame.classList.toggle('is-your-turn', room.status === 'playing' && room.your_turn);
        renderPlayers();
        renderBanner();
        renderResult();
        renderAsk();
        renderBoard();
        renderChat();
        renderActions();
        renderClock();
        schedulePoll();
    }

    function applyState(data, opts) {
        opts = opts || {};
        var previous = room;
        room = data.room || null;
        rememberWaiting(data);
        if (data.me) renderMe(data.me);
        var justFinished = room && room.status === 'finished' && (!previous || previous.status !== 'finished');
        if (!room && previous && !opts.silentClose) {
            showError(previous.status === 'waiting'
                ? 'Phòng đã hết hạn vì không có người vào.'
                : 'Phòng đã đóng.');
        } else if (room && !opts.keepError) {
            showError('');
        }
        render();
        if (justFinished && room.result) celebrate(room.result.outcome);
        if (justFinished) refreshLists();
    }

    function refreshLists() {
        get(boot.urls.lists).then(function (data) {
            renderMe(data.me);
            renderRanks(data.leaderboard);
            renderHistory(data.history);
        }).catch(function () {});
    }

    function act(url, data, opts) {
        if (acting) return;
        acting = true;
        post(url, data).then(function (payload) {
            applyState(payload, opts || {});
        }).catch(function (err) {
            showError(err.message || 'Không thực hiện được.');
            return get(boot.urls.state).then(function (payload) {
                applyState(payload, { keepError: true });
            }).catch(function () {});
        }).finally(function () {
            acting = false;
        });
    }

    function schedulePoll() {
        window.clearTimeout(pollTimer);
        if (!room) return;
        pollTimer = window.setTimeout(poll, 1000);
    }

    function pollSoon() {
        if (polling || acting) return;
        window.clearTimeout(pollTimer);
        pollTimer = window.setTimeout(poll, 150);
    }

    function poll() {
        if (!room || acting || polling) {
            schedulePoll();
            return;
        }
        polling = true;
        get(boot.urls.state).then(function (payload) {
            applyState(payload);
        }).catch(function (err) {
            showError(err.message || 'Mất kết nối. Đang thử lại.');
        }).finally(function () {
            polling = false;
            schedulePoll();
        });
    }

    $('gomoku-create').addEventListener('click', function () {
        showError('');
        act(boot.urls.create, {});
    });
    $('gomoku-join').addEventListener('click', function () {
        showError('');
        act(boot.urls.join, { code: $('gomoku-code').value });
    });
    $('gomoku-code').addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            $('gomoku-join').click();
        }
    });
    $('gomoku-popup-close').addEventListener('click', dismissResult);
    $('gomoku-result').addEventListener('click', function (event) {
        if (event.target === this) dismissResult();
    });
    document.addEventListener('keydown', function (event) {
        if (event.key !== 'Escape') return;
        var askBox = $('gomoku-ask');
        if (askBox && !askBox.hidden) {
            event.preventDefault();
            dismissAsk();
            return;
        }
        var box = $('gomoku-result');
        if (!box || box.hidden) return;
        event.preventDefault();
        dismissResult();
    });

    function dismissResult() {
        resultDismissed = resultStamp();
        var box = $('gomoku-result');
        if (box) box.hidden = true;
        renderAsk();
    }

    $('gomoku-ask-yes').addEventListener('click', function () { answerAsk(true); });
    $('gomoku-ask-no').addEventListener('click', function () { answerAsk(false); });
    $('gomoku-ask-later').addEventListener('click', dismissAsk);
    $('gomoku-ask').addEventListener('click', function (event) {
        if (event.target === this) dismissAsk();
    });

    $('gomoku-chat-form').addEventListener('submit', function (event) {
        event.preventDefault();
        var input = $('gomoku-chat-input');
        var text = input.value.trim();
        if (!text || !room || acting) return;
        input.value = '';
        act(boot.urls.chat, { body: text });
    });

    $('gomoku-copy').addEventListener('click', function () {
        if (!room) return;
        var done = function () { showError(''); };
        var copyBtn = $('gomoku-copy');
        var previous = copyBtn.textContent;
        var markCopied = function () {
            copyBtn.textContent = 'Đã chép';
            window.setTimeout(function () { copyBtn.textContent = previous; }, 1200);
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(room.code).then(function () {
                done();
                markCopied();
            }).catch(function () {
                showError('Không sao chép được. Mã phòng là ' + room.code + '.');
            });
            return;
        }
        showError('Mã phòng là ' + room.code + '.');
    });
    function onFullscreenChange() {
        if (nativeFullscreenElement()) {
            expandNative = true;
            setExpanded(true);
            return;
        }
        if (expandNative) {
            expandNative = false;
            setExpanded(false);
        }
    }

    $('gomoku-expand').addEventListener('click', toggleExpand);
    document.addEventListener('fullscreenchange', onFullscreenChange);
    document.addEventListener('webkitfullscreenchange', onFullscreenChange);

    renderMe(boot.me);
    renderRanks(boot.leaderboard);
    renderHistory(boot.history);
    if (room) rememberWaiting({ server_now: boot.serverNow, room: room });
    render();
    clockTimer = window.setInterval(renderClock, 250);
})();
