/**
 * Overlay loading + % cho trang công cụ (xử lý lâu).
 */
(function (global) {
    'use strict';

    let simTimer = null;

    function els() {
        return {
            root: document.getElementById('jpToolLoading'),
            msg: document.getElementById('jpToolLoadingMsg'),
            bar: document.getElementById('jpToolLoadingBar'),
            pct: document.getElementById('jpToolLoadingPct'),
        };
    }

    function clampPct(value) {
        const n = Number(value);
        if (!Number.isFinite(n)) return 0;
        return Math.max(0, Math.min(100, Math.round(n)));
    }

    function setProgress(percent, message) {
        const { root, msg, bar, pct } = els();
        if (!root) return;
        const p = clampPct(percent);
        if (message && msg) msg.textContent = message;
        if (bar) {
            bar.style.width = `${p}%`;
            bar.setAttribute('aria-valuenow', String(p));
        }
        if (pct) pct.textContent = `${p}%`;
    }

    function show(message, percent) {
        const { root } = els();
        if (!root) return;
        root.classList.remove('d-none');
        root.setAttribute('aria-hidden', 'false');
        document.body.classList.add('jp-tool-loading-active');
        setProgress(percent == null ? 0 : percent, message || 'Đang xử lý…');
    }

    function hide() {
        const { root } = els();
        if (!root) return;
        root.classList.add('d-none');
        root.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('jp-tool-loading-active');
        stopSimulated();
    }

    function stopSimulated() {
        if (simTimer) {
            clearInterval(simTimer);
            simTimer = null;
        }
    }

    function startSimulated(message, maxPct) {
        stopSimulated();
        const cap = maxPct == null ? 92 : clampPct(maxPct);
        let current = 5;
        show(message || 'Đang xử lý…', current);
        simTimer = setInterval(() => {
            if (current >= cap) return;
            current += Math.min(6, cap - current);
            setProgress(current, message);
        }, 350);
    }

    function wireForms() {
        document.querySelectorAll('form.jp-tool-form-loading').forEach((form) => {
            if (form.dataset.jpToolLoadingBound === '1') return;
            form.dataset.jpToolLoadingBound = '1';
            form.addEventListener('submit', () => {
                const msg = form.getAttribute('data-loading-message') || 'Đang xử lý…';
                startSimulated(msg, 94);
            });
        });
    }

    const api = {
        show,
        hide,
        setProgress,
        startSimulated,
        stopSimulated,
        wireForms,
    };

    global.JpToolLoading = api;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wireForms);
    } else {
        wireForms();
    }
})(window);
