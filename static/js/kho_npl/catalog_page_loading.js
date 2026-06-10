/**
 * Loading tức thì cho 4 màn lưới Kho NPL (menu, lọc, phân trang, sắp xếp).
 */
(function (global) {
    'use strict';

    const STORAGE_KEY = 'jp_npl_catalog_loading';
    const MIN_VISIBLE_MS = 300;

    const ROUTE_MESSAGES = {
        '/kho-npl/tong-quan/': 'Đang tải tổng quan…',
        '/kho-npl/danh-muc/': 'Đang tải danh mục…',
        '/kho-npl/ton-kho-npl/': 'Đang tải tồn kho…',
        '/kho-npl/the-kho/': 'Đang tải thẻ kho…',
    };

    let shownAt = 0;
    let hideTimer = null;
    let isVisible = false;
    let globalBound = false;

    function normalizePath(pathname) {
        if (!pathname) return '/';
        return pathname.endsWith('/') ? pathname : pathname + '/';
    }

    function root() {
        return document.getElementById('jpNplCatalogLoading');
    }

    function msgEl() {
        return document.getElementById('jpNplCatalogLoadingMsg');
    }

    function pageMessage() {
        const page = document.querySelector('.jp-npl-material-catalog-page[data-loading-message]');
        if (page) return page.getAttribute('data-loading-message');
        const el = root();
        return (el && el.getAttribute('data-default-message')) || 'Đang tải dữ liệu…';
    }

    function setMessage(message) {
        const el = msgEl();
        if (el && message) el.textContent = message;
    }

    function clearPending() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch (e) {}
        document.documentElement.classList.remove('jp-npl-catalog-pending-load');
    }

    function show(message) {
        const el = root();
        if (!el) return;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        const msg = message || pageMessage();
        setMessage(msg);
        el.classList.remove('d-none');
        el.setAttribute('aria-hidden', 'false');
        document.body.classList.add('jp-npl-catalog-loading-active');
        document.documentElement.classList.add('jp-npl-catalog-pending-load');
        shownAt = Date.now();
        isVisible = true;
    }

    function hide(force) {
        const el = root();
        if (!el || !isVisible) {
            clearPending();
            return;
        }
        const wait = force ? 0 : Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt));
        const run = function () {
            el.classList.add('d-none');
            el.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('jp-npl-catalog-loading-active');
            isVisible = false;
            clearPending();
        };
        if (wait > 0) {
            hideTimer = setTimeout(run, wait);
        } else {
            run();
        }
    }

    function markNavigating(message) {
        const msg = message || pageMessage();
        try {
            sessionStorage.setItem(STORAGE_KEY, msg);
        } catch (e) {}
        show(msg);
    }

    function messageForLink(link, url) {
        if (link.hasAttribute('data-jp-npl-catalog-nav')) {
            return link.getAttribute('data-loading-message') || pageMessage();
        }
        return ROUTE_MESSAGES[normalizePath(url.pathname)] || null;
    }

    function isCatalogListUrl(url) {
        const path = normalizePath(url.pathname);
        if (ROUTE_MESSAGES[path]) return true;
        return false;
    }

    function shouldIgnoreNav(target) {
        if (!target) return true;
        if (target.closest('.jp-npl-mat-col-picker')) return true;
        if (target.closest('.jp-npl-import-modal')) return true;
        if (target.closest('.modal')) return true;
        if (target.closest('.jp-mat-col-resizer')) return true;
        if (target.closest('input[type="checkbox"].npl-ov-col-toggle, input[type="checkbox"].npl-mat-col-toggle, input[type="checkbox"].npl-stk-col-toggle, input[type="checkbox"].npl-sc-col-toggle')) {
            return true;
        }
        return false;
    }

    function wireGlobalNav() {
        if (globalBound) return;
        globalBound = true;

        document.addEventListener('click', function (e) {
            if (shouldIgnoreNav(e.target)) return;

            const sortBtn = e.target.closest('.jp-mat-th-sort');
            if (sortBtn) {
                markNavigating(pageMessage());
                return;
            }

            const catalogRow = e.target.closest('.jp-npl-catalog-row[data-href]');
            if (catalogRow) {
                markNavigating(pageMessage());
                return;
            }

            const link = e.target.closest('a[href]');
            if (!link) return;
            const href = (link.getAttribute('href') || '').trim();
            if (!href || href === '#' || href.startsWith('#') || href.startsWith('javascript:')) return;
            if (link.target === '_blank' || link.hasAttribute('download')) return;

            let url;
            try {
                url = new URL(link.href, window.location.origin);
            } catch (err) {
                return;
            }
            if (url.origin !== window.location.origin) return;

            const msg = messageForLink(link, url);
            if (!msg) return;
            markNavigating(msg);
        }, true);

        document.addEventListener('submit', function (e) {
            const form = e.target;
            if (!form || form.tagName !== 'FORM') return;
            if (shouldIgnoreNav(form)) return;
            if (form.closest('.modal')) return;
            if (form.id === 'jp-npl-import-form') return;
            if (!form.closest('.jp-npl-material-catalog-page')) return;
            const msg = form.getAttribute('data-loading-message') || pageMessage();
            markNavigating(msg);
        }, true);
    }

    function pendingMessage() {
        try {
            return sessionStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function finishAfterPaint() {
        requestAnimationFrame(function () {
            hide(false);
        });
    }

    function onCatalogPageReady() {
        const page = document.querySelector('.jp-npl-material-catalog-page');
        if (!page) return;

        const pending = pendingMessage();
        show(pending || pageMessage());

        if (document.readyState === 'complete') {
            finishAfterPaint();
        } else {
            window.addEventListener('load', finishAfterPaint, { once: true });
        }
    }

    function bootCatalogPage() {
        const pending = pendingMessage();
        if (pending) show(pending);

        if (document.querySelector('.jp-npl-material-catalog-page')) {
            onCatalogPageReady();
        }
    }

    const api = { show, hide, markNavigating };

    global.JpNplCatalogLoading = api;

    wireGlobalNav();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootCatalogPage);
    } else {
        bootCatalogPage();
    }

    window.addEventListener('pageshow', function (e) {
        if (e.persisted) hide(true);
    });
})(window);
