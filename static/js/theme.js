
/**
 * Chuyển kiểu giao diện khung (shell):
 *  - "modern" (mặc định): header đen, menu trắng xám, nền trắng.
 *  - "classic": header đỏ, menu đen, nền trắng (bộ màu cũ).
 * Lưu preference vào localStorage. Nút toggle giữ nhãn "Giao diện tối"/"Giao diện sáng".
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'jp_theme';
    var root = document.documentElement;

    // Giá trị cũ 'dark' được coi như 'classic' để không mất preference người dùng.
    function getShell() {
        try {
            var v = localStorage.getItem(STORAGE_KEY);
            return (v === 'classic' || v === 'dark') ? 'classic' : 'modern';
        } catch (err) {
            return 'modern';
        }
    }

    function updateMeta(shell) {
        var meta = document.querySelector('meta[name="theme-color"]');
        if (!meta) return;
        // classic = header đỏ, modern = header đen
        meta.setAttribute('content', shell === 'classic' ? '#dc2626' : '#111111');
    }

    function updateToggleButtons(shell) {
        document.querySelectorAll('[data-jp-theme-toggle]').forEach(function (btn) {
            var iconDark = btn.querySelector('.jp-theme-icon-dark');
            var iconLight = btn.querySelector('.jp-theme-icon-light');
            var isClassic = shell === 'classic';
            if (iconDark) iconDark.classList.toggle('d-none', isClassic);
            if (iconLight) iconLight.classList.toggle('d-none', !isClassic);
            btn.setAttribute('aria-pressed', isClassic ? 'true' : 'false');
            btn.setAttribute(
                'aria-label',
                isClassic ? 'Bật giao diện sáng' : 'Bật giao diện tối'
            );
            btn.setAttribute('title', isClassic ? 'Giao diện sáng' : 'Giao diện tối');
            var label = btn.querySelector('.jp-theme-toggle-label');
            if (label) {
                label.textContent = isClassic ? 'Giao diện sáng' : 'Giao diện tối';
            }
        });
    }

    function applyShell(shell, persist) {
        if (shell === 'classic') {
            root.setAttribute('data-shell', 'classic');
        } else {
            root.removeAttribute('data-shell');
            shell = 'modern';
        }
        // Đảm bảo không còn dark theme nền-đen cũ.
        root.removeAttribute('data-theme');
        updateMeta(shell);
        updateToggleButtons(shell);
        if (persist) {
            try {
                localStorage.setItem(STORAGE_KEY, shell);
            } catch (err) {
                /* ignore */
            }
        }
    }

    function toggleShell() {
        applyShell(getShell() === 'classic' ? 'modern' : 'classic', true);
    }

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-jp-theme-toggle]');
        if (btn) {
            event.preventDefault();
            toggleShell();
        }
    });

    applyShell(getShell(), false);
})();
