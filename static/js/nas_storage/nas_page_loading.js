/**
 * Popup loading cho các trang NAS trên Portal (thư mục, phân quyền, chia sẻ).
 */
(function (global) {
    'use strict';

    const STORAGE_KEY = 'jp_nas_page_loading';
    const MIN_VISIBLE_MS = 300;

    let shownAt = 0;
    let hideTimer = null;
    let isVisible = false;
    let globalBound = false;

    function root() {
        return document.getElementById('jpNasPageLoading');
    }

    function msgEl() {
        return document.getElementById('jpNasPageLoadingMsg');
    }

    function loadingPageEl() {
        return document.querySelector('.jp-nas-page[data-loading-message]');
    }

    function pageMessage() {
        const page = loadingPageEl();
        if (page) return page.getAttribute('data-loading-message');
        const el = root();
        return (el && el.getAttribute('data-default-message')) || 'Đang tải NAS…';
    }

    function setMessage(message) {
        const el = msgEl();
        if (el && message) el.textContent = message;
    }

    function clearPending() {
        try {
            sessionStorage.removeItem(STORAGE_KEY);
        } catch (e) {}
        document.documentElement.classList.remove('jp-nas-page-pending-load');
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
        document.body.classList.add('jp-nas-page-loading-active');
        document.documentElement.classList.add('jp-nas-page-pending-load');
        shownAt = Date.now();
        isVisible = true;
    }

    function hide(force) {
        const el = root();
        if (!el || !isVisible) {
            clearPending();
            document.body.classList.remove('jp-nas-page-loading-active');
            if (el) {
                el.classList.add('d-none');
                el.setAttribute('aria-hidden', 'true');
            }
            return;
        }
        const wait = force ? 0 : Math.max(0, MIN_VISIBLE_MS - (Date.now() - shownAt));
        const run = function () {
            el.classList.add('d-none');
            el.setAttribute('aria-hidden', 'true');
            document.body.classList.remove('jp-nas-page-loading-active');
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

    function shouldIgnoreNav(target) {
        if (!target) return true;
        if (target.closest('[data-no-loading]')) return true;
        if (target.closest('.modal')) return true;
        if (target.closest('.offcanvas')) return true;
        if (target.closest('.jp-nas-share-modal')) return true;
        return false;
    }

    function messageForLink(link) {
        if (link.hasAttribute('data-loading-message')) {
            return link.getAttribute('data-loading-message');
        }
        return pageMessage();
    }

    function wireGlobalNav() {
        if (globalBound) return;
        globalBound = true;

        document.addEventListener('click', function (e) {
            if (shouldIgnoreNav(e.target)) return;

            const link = e.target.closest('a[href]');
            if (!link) return;
            const href = (link.getAttribute('href') || '').trim();
            if (!href || href === '#' || href.startsWith('#') || href.startsWith('javascript:')) return;
            if (link.target === '_blank' || link.hasAttribute('download')) return;
            if (link.hasAttribute('data-no-loading')) return;

            let url;
            try {
                url = new URL(link.href, window.location.origin);
            } catch (err) {
                return;
            }
            if (url.origin !== window.location.origin) return;

            markNavigating(messageForLink(link));
        }, true);

        document.addEventListener('submit', function (e) {
            const form = e.target;
            if (!form || form.tagName !== 'FORM') return;
            if (shouldIgnoreNav(form)) return;
            if (form.closest('.modal')) return;
            if (form.hasAttribute('data-no-loading')) return;
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
        const page = loadingPageEl();
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
        if (loadingPageEl()) {
            onLoadingPageReady();
            return;
        }
        if (pendingMessage()) {
            hide(true);
        }
    }

    const api = { show, hide, markNavigating };

    global.JpNasPageLoading = api;

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
