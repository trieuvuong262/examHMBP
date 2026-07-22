/**
 * Django flash messages (includes/flash_messages.html) — tự ẩn sau 3 giây.
 * Áp dụng toàn portal qua base.html.
 */
(function () {
    var DEFAULT_MS = 3000;

    function dismissAlert(el) {
        if (!el || el.dataset.jpFlashDismissed === '1') return;
        el.dataset.jpFlashDismissed = '1';
        if (window.bootstrap && bootstrap.Alert) {
            bootstrap.Alert.getOrCreateInstance(el).close();
            return;
        }
        el.classList.remove('show');
        window.setTimeout(function () {
            if (el.parentNode) el.parentNode.removeChild(el);
        }, 150);
    }

    function initFlashMessages() {
        document.querySelectorAll('.jp-flash-alert').forEach(function (el) {
            var ms = parseInt(el.getAttribute('data-jp-flash-ms') || String(DEFAULT_MS), 10);
            if (!ms || ms < 500) ms = DEFAULT_MS;
            window.setTimeout(function () {
                dismissAlert(el);
            }, ms);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initFlashMessages);
    } else {
        initFlashMessages();
    }
})();
