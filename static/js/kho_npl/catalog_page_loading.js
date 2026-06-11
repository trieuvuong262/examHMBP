/**
 * Loading tức thì cho màn lưới Kho NPL và màn kiểm kê (tải tồn / bảng lớn).
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
        '/kho-npl/phieu-nhap/': 'Đang tải phiếu nhập…',
        '/kho-npl/phieu-xuat/': 'Đang tải phiếu xuất…',
        '/kho-npl/chuyen-kho/': 'Đang tải phiếu chuyển…',
        '/kho-npl/phieu-huy/': 'Đang tải phiếu hủy…',
        '/kho-npl/kiem-ke/': 'Đang tải phiếu kiểm kê…',
    };

    const STOCKTAKE_ROUTE_PATTERNS = [
        [/^\/kho-npl\/kiem-ke\/\d+\/nhap-so\/$/, 'Đang tải bảng kiểm kê…'],
        [/^\/kho-npl\/kiem-ke\/\d+\/$/, 'Đang tải chi tiết kiểm kê…'],
    ];

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

    function loadingPageEl() {
        return document.querySelector('.jp-npl-material-catalog-page[data-loading-message]')
            || document.querySelector('.jp-npl-stocktake-page[data-loading-message]');
    }

    function pageMessage() {
        const page = loadingPageEl();
        if (page) return page.getAttribute('data-loading-message');
        const el = root();
        return (el && el.getAttribute('data-default-message')) || 'Đang tải dữ liệu…';
    }

    function stocktakeRouteMessage(path) {
        for (let i = 0; i < STOCKTAKE_ROUTE_PATTERNS.length; i += 1) {
            const pattern = STOCKTAKE_ROUTE_PATTERNS[i];
            if (pattern[0].test(path)) return pattern[1];
        }
        return null;
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
        if (link.hasAttribute('data-loading-message')) {
            return link.getAttribute('data-loading-message');
        }
        if (link.hasAttribute('data-jp-npl-catalog-nav')) {
            return link.getAttribute('data-loading-message') || pageMessage();
        }
        const path = normalizePath(url.pathname);
        return stocktakeRouteMessage(path) || ROUTE_MESSAGES[path] || null;
    }

    function shouldIgnoreNav(target) {
        if (!target) return true;
        if (target.closest('.jp-npl-mat-col-picker')) return true;
        if (target.closest('.jp-npl-import-modal')) return true;
        if (target.closest('.modal')) return true;
        if (target.closest('.jp-mat-col-resizer')) return true;
        if (target.closest('input[type="checkbox"][class*="-col-toggle"]')) {
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
            const inCatalog = form.closest('.jp-npl-material-catalog-page');
            const inStocktake = form.closest('.jp-npl-stocktake-page');
            if (!inCatalog && !inStocktake && !form.hasAttribute('data-loading-message')) return;
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

    function onLoadingPageReady() {
        const catalogPage = document.querySelector('.jp-npl-material-catalog-page');
        const stocktakePage = document.querySelector('.jp-npl-stocktake-page[data-loading-message]');
        const page = catalogPage || stocktakePage;
        if (!page) return;

        const pending = pendingMessage();
        show(pending || page.getAttribute('data-loading-message') || pageMessage());

        if (document.readyState === 'complete') {
            finishAfterPaint();
        } else {
            window.addEventListener('load', finishAfterPaint, { once: true });
        }
    }

    function bootLoadingPages() {
        const catalogPage = document.querySelector('.jp-npl-material-catalog-page');
        const stocktakePage = document.querySelector('.jp-npl-stocktake-page[data-loading-message]');
        if (catalogPage || stocktakePage) {
            onLoadingPageReady();
            return;
        }
        if (pendingMessage()) {
            hide(true);
        }
    }

    const api = { show, hide, markNavigating };

    global.JpNplCatalogLoading = api;

    wireGlobalNav();

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootLoadingPages);
    } else {
        bootLoadingPages();
    }

    window.addEventListener('pageshow', function (e) {
        if (e.persisted) hide(true);
    });
})(window);
