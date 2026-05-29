/**
 * Dark mode — lưu preference localStorage, sidebar chuyển sang nền đỏ.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'jp_theme';
    var root = document.documentElement;

    function getTheme() {
        try {
            return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
        } catch (err) {
            return 'light';
        }
    }

    function updateMeta(theme) {
        var meta = document.querySelector('meta[name="theme-color"]');
        if (!meta) return;
        meta.setAttribute('content', theme === 'dark' ? '#450a0a' : '#dc2626');
    }

    function updateToggleButtons(theme) {
        document.querySelectorAll('[data-jp-theme-toggle]').forEach(function (btn) {
            var iconDark = btn.querySelector('.jp-theme-icon-dark');
            var iconLight = btn.querySelector('.jp-theme-icon-light');
            var isDark = theme === 'dark';
            if (iconDark) iconDark.classList.toggle('d-none', isDark);
            if (iconLight) iconLight.classList.toggle('d-none', !isDark);
            btn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
            btn.setAttribute(
                'aria-label',
                isDark ? 'Bật giao diện sáng' : 'Bật giao diện tối'
            );
            btn.setAttribute('title', isDark ? 'Giao diện sáng' : 'Giao diện tối');
        });
    }

    function applyTheme(theme, persist) {
        if (theme === 'dark') {
            root.setAttribute('data-theme', 'dark');
        } else {
            root.removeAttribute('data-theme');
            theme = 'light';
        }
        updateMeta(theme);
        updateToggleButtons(theme);
        if (persist) {
            try {
                localStorage.setItem(STORAGE_KEY, theme);
            } catch (err) {
                /* ignore */
            }
        }
    }

    function toggleTheme() {
        applyTheme(getTheme() === 'dark' ? 'light' : 'dark', true);
    }

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-jp-theme-toggle]');
        if (btn) {
            event.preventDefault();
            toggleTheme();
        }
    });

    applyTheme(getTheme(), false);
})();
