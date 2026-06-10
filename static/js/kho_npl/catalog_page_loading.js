/**
 * Overlay loading cho các màn lưới Kho NPL (tổng quan, danh mục, tồn kho, thẻ kho).
 */
(function (global) {
    'use strict';

    const STORAGE_KEY = 'jp_npl_catalog_loading';
    const MIN_VISIBLE_MS = 280;

    let shownAt = 0;
    let hideTimer = null;

    function root() {
        return document.getElementById('jpNplCatalogLoading');
    }

    function msgEl() {
        return document.getElementById('jpNplCatalogLoadingMsg');
    }

    function defaultMessage() {
        const el = root();
        return (el && el.getAttribute('data-default-message')) || 'Đang tải dữ liệu…';
    }

    function setMessage(message) {
        const el = msgEl();
        if (el && message) el.textContent = message;
    }

    function show(message) {
        const el = root();
        if (!el) return;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        setMessage(message || defaultMessage());
        el.classList.remove('d-none');
        el.setAttribute('aria-hidden', 'false');
        document.body.classList.add('jp-npl-catalog-loading-active');
        shownAt = Date.now();
    }

    function hide(force) {
        const el = root();
        if (!el) return;
        const wait = force ? 0 : Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt));
        const run = function () {
            el.classList.add('d-none');
            el.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('jp-npl-catalog-loading-active');
            try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
        };
        if (wait > 0) {
            hideTimer = setTimeout(run, wait);
        } else {
            run();
        }
    }

    function markNavigating(message) {
        try {
            sessionStorage.setItem(STORAGE_KEY, message || defaultMessage());
        } catch (e) {}
        show(message);
    }

    function shouldIgnoreClick(target) {
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

    function wirePage() {
        const page = document.querySelector('.jp-npl-material-catalog-page');
        if (!page || page.dataset.jpCatalogLoadingBound === '1') return;
        page.dataset.jpCatalogLoadingBound = '1';

        page.addEventListener('submit', function (e) {
            const form = e.target;
            if (!form || form.tagName !== 'FORM') return;
            if (shouldIgnoreClick(form)) return;
            if (form.closest('.modal')) return;
            if (form.id === 'jp-npl-import-form') return;
            const msg = form.getAttribute('data-loading-message') || defaultMessage();
            markNavigating(msg);
        });

        page.addEventListener('click', function (e) {
            if (shouldIgnoreClick(e.target)) return;

            const sortBtn = e.target.closest('.jp-mat-th-sort');
            if (sortBtn) {
                markNavigating(defaultMessage());
                return;
            }

            const catalogRow = e.target.closest('.jp-npl-catalog-row[data-href]');
            if (catalogRow) {
                markNavigating(defaultMessage());
                return;
            }

            const link = e.target.closest('a[href]');
            if (!link) return;
            const href = (link.getAttribute('href') || '').trim();
            if (!href || href === '#' || href.startsWith('#') || href.startsWith('javascript:')) return;
            if (link.target === '_blank' || link.hasAttribute('download')) return;
            markNavigating(defaultMessage());
        });
    }

    function initFromStorage() {
        try {
            const pending = sessionStorage.getItem(STORAGE_KEY);
            if (pending) show(pending);
        } catch (e) {}
    }

    function onReady() {
        wirePage();
        if (!root()) return;
        if (root().classList.contains('d-none')) {
            initFromStorage();
        }
        hide(false);
    }

    const api = { show, hide, markNavigating };

    global.JpNplCatalogLoading = api;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onReady);
    } else {
        onReady();
    }

    window.addEventListener('pageshow', function (e) {
        if (e.persisted) hide(true);
    });
})(window);
