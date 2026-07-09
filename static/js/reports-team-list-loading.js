/**
 * Popup loading cho danh sách báo cáo VP / SX (lọc, sắp xếp, mở chi tiết).
 */
(function () {
    'use strict';

    var overlay = document.getElementById('jp-team-list-loading');
    if (!overlay) return;

    if (overlay.parentNode !== document.body) {
        document.body.appendChild(overlay);
    }

    var msgEl = overlay.querySelector('[data-team-loading-message]');

    function show(message) {
        if (msgEl && message) {
            msgEl.textContent = message;
        }
        overlay.hidden = false;
        overlay.setAttribute('aria-busy', 'true');
        document.body.classList.add('jp-team-list-loading');
    }

    function hide() {
        overlay.hidden = true;
        overlay.setAttribute('aria-busy', 'false');
        document.body.classList.remove('jp-team-list-loading');
    }

    window.JpTeamListLoading = {
        show: show,
        hide: hide,
    };

    window.addEventListener('pageshow', function (ev) {
        if (ev.persisted) {
            hide();
        }
    });
})();
