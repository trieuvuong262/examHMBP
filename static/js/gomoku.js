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

    function opposite(color) {
        return color === 'black' ? 'white' : 'black';
    }

    function colorLabel(color) {
        return color === 'black' ? 'Đen' : 'Trắng';
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
            tr.innerHTML =
                '<td>' + medal + '</td>' +
                '<td>' + escapeHtml(row.name) + '</td>' +
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

    function seatHtml(name, color, active, waiting) {
        var state = waiting ? ' is-wait' : (active ? ' is-turn' : '');
        var note = waiting ? 'Đang chờ' : (colorLabel(color) + (active ? ' · đang đi' : ''));
        return '<div class="gomoku-seat' + state + '">' +
            '<span class="gomoku-stone-icon ' + color + '"></span>' +
            '<span><strong>' + escapeHtml(name) + '</strong><span>' + escapeHtml(note) + '</span></span>' +
            '</div>';
    }

    function renderPlayers() {
        var key = [room.your_name, room.opponent_name, room.your_color, room.your_turn, room.status].join('|');
        if (key === playersKey) return;
        playersKey = key;
        var youActive = room.status === 'playing' && room.your_turn;
        var oppActive = room.status === 'playing' && !room.your_turn && !!room.opponent_name;
        $('gomoku-players').innerHTML =
            seatHtml(room.your_name, room.your_color, youActive, false) +
            seatHtml(room.opponent_name || 'Chưa có người', opposite(room.your_color), oppActive, !room.opponent_name);
    }

    function renderBanner() {
        var banner = $('gomoku-banner');
        var text = '';
        var tone = '';
        if (room && room.status === 'waiting') {
            tone = '';
            text = 'Đọc mã phòng cho đồng nghiệp. Không có người vào thì phòng tự hủy.';
        } else if (room && room.status === 'playing' && room.draw_offer === 'you') {
            tone = 'is-info';
            text = 'Bạn đã xin hòa. Đồng hồ lượt vẫn chạy.';
        } else if (room && room.status === 'playing' && room.draw_offer === 'opponent') {
            tone = 'is-info';
            text = 'Đối thủ xin hòa. Đồng hồ lượt vẫn chạy.';
        } else if (room && room.status === 'finished' && room.result) {
            var result = room.result;
            tone = 'is-' + result.outcome;
            text = result.outcome_label + ' · ' + result.reason_label + '. Elo ' +
                result.elo_before + ' → ' + result.elo_after + ' (' + deltaText(result.elo_delta) + ')';
            if (room.you_rematch && !room.opponent_rematch) text += ' Đang chờ đối thủ chơi lại.';
            else if (room.opponent_rematch && !room.you_rematch) text += ' Đối thủ muốn chơi lại.';
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

    function renderResult() {
        var box = $('gomoku-result');
        if (!box) return;
        if (!room || room.status !== 'finished' || !room.result) {
            box.hidden = true;
            box.textContent = '';
            return;
        }
        var result = room.result;
        box.hidden = false;
        box.className = 'gomoku-result is-' + result.outcome;
        box.innerHTML = '<strong>' + escapeHtml(result.outcome_label) + '</strong><span>' +
            escapeHtml(result.reason_label) + ' · ' + deltaText(result.elo_delta) + ' Elo</span>';
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
        var key = [room.status, room.draw_offer, room.you_rematch, room.opponent_rematch].join('|');
        if (key === actionsKey) return;
        actionsKey = key;
        var box = $('gomoku-actions');
        box.textContent = '';
        if (!room) return;
        if (room.status === 'waiting') {
            box.appendChild(button('Hủy phòng', 'btn btn-outline-danger', function () {
                act(boot.urls.leave, {}, { silentClose: true });
            }));
            return;
        }
        if (room.status === 'playing') {
            if (room.draw_offer === 'opponent') {
                box.appendChild(button('Đồng ý hòa', 'btn btn-outline-secondary', function () {
                    act(boot.urls.draw, { action: 'accept' });
                }));
                box.appendChild(button('Từ chối', 'btn btn-outline-secondary', function () {
                    act(boot.urls.draw, { action: 'decline' });
                }));
            } else if (room.draw_offer !== 'you') {
                box.appendChild(button('Xin hòa', 'btn btn-outline-secondary', function () {
                    act(boot.urls.draw, { action: 'offer' });
                }));
            }
            box.appendChild(button('Đầu hàng', 'btn btn-outline-danger', function () {
                if (!window.confirm('Đầu hàng ván này?')) return;
                act(boot.urls.resign, {});
            }));
            return;
        }
        if (room.status === 'finished') {
            var again = button(room.you_rematch ? 'Đang chờ đối thủ' : 'Chơi lại', 'btn btn-hm', function () {
                act(boot.urls.rematch, {});
            });
            again.disabled = room.you_rematch;
            box.appendChild(again);
            box.appendChild(button('Rời phòng', 'btn btn-outline-secondary', function () {
                act(boot.urls.leave, {}, { silentClose: true });
            }));
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
            label.textContent = room.your_turn ? 'Lượt của bạn' : 'Lượt của đối thủ';
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

    function render() {
        var inRoom = !!room;
        var page = document.querySelector('.gomoku-page');
        if (page) page.classList.toggle('is-match', inRoom);
        $('gomoku-lobby').classList.toggle('d-none', inRoom);
        $('gomoku-match').classList.toggle('d-none', !inRoom);
        if (!inRoom) {
            boardKey = '';
            playersKey = '';
            bannerKey = '';
            actionsKey = '';
            var frameIdle = $('gomoku-frame');
            if (frameIdle) frameIdle.classList.remove('is-your-turn');
            schedulePoll();
            return;
        }
        renderCode();
        var frame = $('gomoku-frame');
        if (frame) frame.classList.toggle('is-your-turn', room.status === 'playing' && room.your_turn);
        renderPlayers();
        renderBanner();
        renderResult();
        renderBoard();
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

    renderMe(boot.me);
    renderRanks(boot.leaderboard);
    renderHistory(boot.history);
    if (room) rememberWaiting({ server_now: boot.serverNow, room: room });
    render();
    clockTimer = window.setInterval(renderClock, 250);
})();
