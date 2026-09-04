/**
 * Popup loading — danh sách VP/SX, Nhân sự, sửa NV, reset MK, KPI.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'jp_team_list_loading';
    var MIN_VISIBLE_MS = 280;
    var TEAM_LIST_PATHS = ['/reports/sx/team/', '/reports/vp/team/'];
    var HRM_LIST_PATH = '/dashboard/users/';

    var overlay = document.getElementById('jp-team-list-loading');
    if (!overlay) return;

    if (overlay.parentNode !== document.body) {
        document.body.appendChild(overlay);
    }

    var msgEl = overlay.querySelector('[data-team-loading-message]');
    var shownAt = 0;
    var hideTimer = null;
    var isVisible = false;
    var globalBound = false;

    function normalizePath(pathname) {
        if (!pathname) return '/';
        return pathname.endsWith('/') ? pathname : pathname + '/';
    }

    function isTeamListUrl(url) {
        var path = normalizePath(url.pathname);
        for (var i = 0; i < TEAM_LIST_PATHS.length; i += 1) {
            if (path === TEAM_LIST_PATHS[i]) return true;
        }
        return false;
    }

    function isHrmListUrl(url) {
        return normalizePath(url.pathname) === HRM_LIST_PATH;
    }

    function isHrmUserEditUrl(url) {
        return /^\/dashboard\/users\/edit\/\d+\/?$/.test(url.pathname);
    }

    function isKpiUrl(url) {
        var path = url.pathname || '';
        if (path.indexOf('/kpi/import-excel/sample') === 0) return false;
        return path === '/kpi' || path.indexOf('/kpi/') === 0;
    }

    function isNavListUrl(url) {
        return isTeamListUrl(url) || isHrmListUrl(url) || isKpiUrl(url);
    }

    function clearPending() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch (e) {}
        document.documentElement.classList.remove('jp-team-list-pending-load');
    }

    function show(message) {
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        if (msgEl && message) {
            msgEl.textContent = message;
        }
        overlay.hidden = false;
        overlay.setAttribute('aria-busy', 'true');
        document.body.classList.add('jp-team-list-loading');
        document.documentElement.classList.add('jp-team-list-pending-load');
        shownAt = Date.now();
        isVisible = true;
    }

    function hide(force) {
        if (!isVisible) {
            clearPending();
            document.body.classList.remove('jp-team-list-loading');
            overlay.hidden = true;
            overlay.setAttribute('aria-busy', 'false');
            return;
        }
        var wait = force ? 0 : Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt));
        var run = function () {
            overlay.hidden = true;
            overlay.setAttribute('aria-busy', 'false');
            document.body.classList.remove('jp-team-list-loading');
            isVisible = false;
            clearPending();
        };
        if (wait > 0) {
            hideTimer = setTimeout(run, wait);
        } else {
            run();
        }
    }

    function pendingMessage() {
        try {
            return sessionStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function markNavigating(message) {
        var msg = message || 'Đang tải danh sách...';
        try {
            sessionStorage.setItem(STORAGE_KEY, msg);
        } catch (e) {}
        show(msg);
    }

    function messageForKpiUrl(url, explicit) {
        if (explicit) return explicit;
        var path = url.pathname || '';
        if (/\/kpi\/detail\//.test(path)) return 'Đang tải bảng đánh giá KPI…';
        if (/\/kpi\/import-excel/.test(path)) return 'Đang mở trang giao KPI…';
        if (/\/kpi\/tong-ket/.test(path)) return 'Đang tải tổng kết KPI…';
        return 'Đang tải danh sách KPI…';
    }

    function messageForLink(link, url) {
        if (link.hasAttribute('data-jp-team-list-nav')) {
            return link.getAttribute('data-loading-message') || 'Đang tải danh sách...';
        }
        if (isHrmUserEditUrl(url)) {
            return 'Đang tải thông tin nhân viên...';
        }
        if (isKpiUrl(url)) {
            return messageForKpiUrl(url, link.getAttribute('data-loading-message'));
        }
        if (isNavListUrl(url)) {
            if (isHrmListUrl(url)) {
                return 'Đang tải danh sách nhân sự...';
            }
            return 'Đang tải danh sách...';
        }
        return null;
    }

    function wireGlobalNav() {
        if (globalBound) return;
        globalBound = true;

        document.addEventListener('click', function (e) {
            var link = e.target.closest('a[href]');
            if (!link) return;
            if (link.target === '_blank' || link.hasAttribute('download')) return;

            var href = (link.getAttribute('href') || '').trim();
            if (!href || href === '#' || href.charAt(0) === '#') return;

            var url;
            try {
                url = new URL(link.href, window.location.origin);
            } catch (err) {
                return;
            }
            if (url.origin !== window.location.origin) return;

            var msg = messageForLink(link, url);
            if (!msg) return;
            markNavigating(msg);
        }, true);

        document.addEventListener('submit', function (e) {
            var form = e.target;
            if (!form || form.tagName !== 'FORM') return;
            if (form.getAttribute('data-skip-loading') === '1') return;
            if (!(form.closest && form.closest('.jp-kpi-page'))) return;
            var msg = form.getAttribute('data-loading-message') || 'Đang xử lý KPI…';
            markNavigating(msg);
        }, true);
    }

    function finishAfterPaint() {
        requestAnimationFrame(function () {
            hide(false);
        });
    }

    function bootListPage() {
        var page = document.querySelector(
            '.jp-team-list-page, .jp-hrm-list-page, .jp-user-form-page, .jp-kpi-page',
        );
        if (!page) {
            if (pendingMessage()) {
                hide(true);
            }
            return;
        }

        var pending = pendingMessage();
        if (pending) {
            show(pending);
        }

        if (document.readyState === 'complete') {
            finishAfterPaint();
        } else {
            window.addEventListener('load', finishAfterPaint, { once: true });
        }
    }

    window.JpTeamListLoading = {
        show: show,
        hide: hide,
        markNavigating: markNavigating,
    };

    wireGlobalNav();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootListPage);
    } else {
        bootListPage();
    }

    window.addEventListener('pageshow', function (ev) {
        if (ev.persisted) {
            hide(true);
        }
    });
})();
