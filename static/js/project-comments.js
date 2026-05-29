(function () {
    'use strict';

    function loadMembers() {
        var el = document.getElementById('jp-mention-members');
        if (!el || !el.textContent) return [];
        try {
            return JSON.parse(el.textContent);
        } catch (e) {
            return [];
        }
    }

    function filterMembers(members, query) {
        var q = (query || '').toLowerCase();
        if (!q) return members.slice(0, 8);
        return members.filter(function (m) {
            return m.username.toLowerCase().indexOf(q) !== -1
                || (m.full_name || '').toLowerCase().indexOf(q) !== -1
                || (m.label || '').toLowerCase().indexOf(q) !== -1;
        }).slice(0, 8);
    }

    function getMentionQuery(textarea) {
        var value = textarea.value;
        var pos = textarea.selectionStart;
        var before = value.slice(0, pos);
        var match = before.match(/@([a-zA-Z0-9_\.\u00C0-\u1EF9]*)$/u);
        if (!match) return null;
        return {
            query: match[1] || '',
            start: pos - match[0].length,
            end: pos,
        };
    }

    function initMentionInput(textarea, members) {
        var box = textarea.closest('.jp-mention-wrap') || textarea.parentElement;
        if (!box) return;

        var list = document.createElement('ul');
        list.className = 'jp-mention-suggest list-unstyled mb-0';
        list.hidden = true;
        box.classList.add('jp-mention-wrap');
        box.appendChild(list);

        var activeCtx = null;

        function hideList() {
            list.hidden = true;
            list.innerHTML = '';
            activeCtx = null;
        }

        function insertMention(username) {
            if (!activeCtx) return;
            var value = textarea.value;
            var insert = '@' + username + ' ';
            textarea.value = value.slice(0, activeCtx.start) + insert + value.slice(activeCtx.end);
            var cursor = activeCtx.start + insert.length;
            textarea.focus();
            textarea.setSelectionRange(cursor, cursor);
            hideList();
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }

        function renderList(items) {
            list.innerHTML = '';
            if (!items.length) {
                hideList();
                return;
            }
            items.forEach(function (m) {
                var li = document.createElement('li');
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'jp-mention-suggest-item';
                btn.innerHTML = '<strong>' + m.full_name + '</strong><span class="text-muted"> @' + m.username + '</span>';
                btn.addEventListener('mousedown', function (e) {
                    e.preventDefault();
                    insertMention(m.username);
                });
                li.appendChild(btn);
                list.appendChild(li);
            });
            list.hidden = false;
        }

        function refresh() {
            var ctx = getMentionQuery(textarea);
            if (!ctx) {
                hideList();
                return;
            }
            activeCtx = ctx;
            renderList(filterMembers(members, ctx.query));
        }

        textarea.addEventListener('input', refresh);
        textarea.addEventListener('keyup', refresh);
        textarea.addEventListener('click', refresh);
        textarea.addEventListener('blur', function () {
            setTimeout(hideList, 150);
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        var members = loadMembers();
        if (!members.length) return;
        document.querySelectorAll('[data-jp-mention-input]').forEach(function (textarea) {
            initMentionInput(textarea, members);
        });
    });
})();
