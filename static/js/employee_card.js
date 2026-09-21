/**
 * Thẻ thông tin nhân viên — bấm tên trên danh sách tổ / thống kê.
 */
(function () {
    'use strict';

    function text(el, value) {
        if (el) el.textContent = value || '—';
    }

    function showRow(key, hasValue) {
        var row = document.querySelector('#jpEmployeeCardModal [data-emp-row="' + key + '"]');
        if (!row) return;
        row.classList.toggle('d-none', !hasValue);
    }

    function dash(value) {
        var s = (value || '').trim();
        if (!s || s === '---' || s === '—') return '';
        return s;
    }

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-jp-emp-card]');
        if (!btn) return;
        event.preventDefault();
        event.stopPropagation();

        var modalEl = document.getElementById('jpEmployeeCardModal');
        if (!modalEl || !window.bootstrap) return;

        var name = dash(btn.getAttribute('data-name')) || 'Nhân viên';
        var code = dash(btn.getAttribute('data-code'));
        var username = dash(btn.getAttribute('data-username'));
        var phone = dash(btn.getAttribute('data-phone'));
        var dept = dash(btn.getAttribute('data-dept'));
        var division = dash(btn.getAttribute('data-division'));
        var jobTitle = dash(btn.getAttribute('data-job-title'));
        var jobPosition = dash(btn.getAttribute('data-job-position'));
        var join = dash(btn.getAttribute('data-join'));
        var gender = dash(btn.getAttribute('data-gender'));
        var probation = btn.getAttribute('data-probation') === '1';
        var avatar = dash(btn.getAttribute('data-avatar'));
        var profileUrl = dash(btn.getAttribute('data-profile-url'));

        text(document.getElementById('jpEmployeeCardTitle'), name);
        text(document.getElementById('jpEmpCardName'), name);

        var metaParts = [];
        if (code) metaParts.push(code);
        if (username) metaParts.push(username);
        text(document.getElementById('jpEmpCardMeta'), metaParts.join(' · '));

        text(document.getElementById('jpEmpCardCode'), code);
        text(document.getElementById('jpEmpCardUsername'), username);
        text(document.getElementById('jpEmpCardPhone'), phone);
        text(document.getElementById('jpEmpCardDept'), dept);
        text(document.getElementById('jpEmpCardDivision'), division);
        text(document.getElementById('jpEmpCardJobTitle'), jobTitle);
        text(document.getElementById('jpEmpCardJobPosition'), jobPosition);
        text(document.getElementById('jpEmpCardJoin'), join);
        text(document.getElementById('jpEmpCardGender'), gender);
        text(document.getElementById('jpEmpCardStatus'), probation ? 'Thử việc' : 'Chính thức');

        showRow('code', !!code);
        showRow('username', !!username);
        showRow('phone', !!phone);
        showRow('dept', !!dept);
        showRow('division', !!division);
        showRow('job-title', !!jobTitle);
        showRow('job-position', !!jobPosition);
        showRow('join', !!join);
        showRow('gender', !!gender);
        showRow('status', true);

        var img = document.getElementById('jpEmpCardAvatarImg');
        var fallback = document.getElementById('jpEmpCardAvatarFallback');
        if (img && fallback) {
            if (avatar) {
                img.src = avatar;
                img.alt = name;
                img.classList.remove('d-none');
                fallback.classList.add('d-none');
            } else {
                img.removeAttribute('src');
                img.classList.add('d-none');
                fallback.textContent = (name.charAt(0) || '?').toUpperCase();
                fallback.classList.remove('d-none');
            }
        }

        var link = document.getElementById('jpEmpCardProfileLink');
        if (link) {
            if (profileUrl) {
                link.href = profileUrl;
                link.classList.remove('d-none');
            } else {
                link.classList.add('d-none');
                link.removeAttribute('href');
            }
        }

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    });
})();
