/**
 * Overlay loading cho các màn lưới Kho NPL (tổng quan, danh mục, tồn kho, thẻ kho).
 */
(function (global) {
    'use strict';

    const STORAGE_KEY = 'jp_npl_catalog_loading';
    const MIN_VISIBLE_MS = 450;

    let shownAt = 0;
    let hideTimer = null;
    let isVisible = false;

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

    function clearPending() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch (e) {}
        document.documentElement.classList.remove('jp-npl-catalog-pending-load');
        const early = document.getElementById('jpNplCatalogLoadingEarly');
        if (early) early.remove();
    }

    function show(message) {
        const el = root();
        if (!el) return;
        if (hideTimer) {
            clearTimeout(hideTimer);
            hideTimer = null;
        }
        const early = document.getElementById('jpNplCatalogLoadingEarly');
        if (early) early.remove();
        setMessage(message || defaultMessage());
        el.classList.remove('d-none');
        el.setAttribute('aria-hidden', 'false');
        document.body.classList.add('jp-npl-catalog-loading-active');
        document.documentElement.classList.add('jp-npl-catalog-pending-load');
        shownAt = window.__jpNplCatalogLoadingStart || Date.now();
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
        const msg = message || defaultMessage();
        try {
            sessionStorage.setItem(STORAGE_KEY, msg);
        } catch (e) {}
        show(msg);
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

    function pendingMessage() {
        try {
            return sessionStorage.getItem(STORAGE_KEY);
        } catch (e) {
            return null;
        }
    }

    function finishAfterPaint() {
        requestAnimationFrame(function () {
            requestAnimationFrame(function () {
                hide(false);
            });
        });
    }

    function onReady() {
        wirePage();
        const el = root();
        if (!el) return;

        const pending = pendingMessage();
        if (pending) {
            setMessage(pending);
        }
        if (!isVisible) {
            show(pending || defaultMessage());
        }

        if (document.readyState === 'complete') {
            finishAfterPaint();
        } else {
            window.addEventListener('load', finishAfterPaint, { once: true });
        }
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
