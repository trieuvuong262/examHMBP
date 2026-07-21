/**
 * Sidebar thu gọn / mở rộng (desktop) — lưu preference localStorage.
 */
(function () {
    'use strict';

    var STORAGE_KEY = 'jp_sidebar_collapsed';

    function isCollapsed() {
        return document.documentElement.classList.contains('jp-sidebar-collapsed');
    }

    function setCollapsed(collapsed) {
        document.documentElement.classList.toggle('jp-sidebar-collapsed', collapsed);
        try {
            localStorage.setItem(STORAGE_KEY, collapsed ? '1' : '0');
        } catch (e) {}

        document.querySelectorAll('[data-jp-sidebar-collapse]').forEach(function (btn) {
            btn.setAttribute('aria-pressed', collapsed ? 'true' : 'false');
            btn.setAttribute('aria-label', collapsed ? 'Mở rộng menu' : 'Thu gọn menu');
            btn.setAttribute('title', collapsed ? 'Mở rộng menu' : 'Thu gọn menu');
        });

        if (!collapsed) {
            closeAllFlyouts();
        }
    }

    function closeAllFlyouts() {
        document.querySelectorAll('.jp-sidebar-group.is-flyout-open').forEach(function (group) {
            group.classList.remove('is-flyout-open');
        });
    }

    function bindCollapseToggle() {
        document.querySelectorAll('[data-jp-sidebar-collapse]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                setCollapsed(!isCollapsed());
            });
        });
    }

    function bindFlyouts() {
        document.querySelectorAll('[data-jp-sidebar-group-toggle]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (!isCollapsed() || window.innerWidth < 992) return;
                var group = btn.closest('.jp-sidebar-group');
                if (!group) return;
                var open = group.classList.contains('is-flyout-open');
                closeAllFlyouts();
                if (!open) {
                    group.classList.add('is-flyout-open');
                    btn.setAttribute('aria-expanded', 'true');
                }
            });
        });

        document.addEventListener('click', function (e) {
            if (!isCollapsed()) return;
            if (e.target.closest('.jp-sidebar-group')) return;
            closeAllFlyouts();
        });
    }

    function applyLinkTitles() {
        document.querySelectorAll('.jp-sidebar-link, .jp-sidebar-group-toggle').forEach(function (el) {
            if (el.getAttribute('data-jp-title-bound') === '1') return;
            var label = el.querySelector('span:not(.jp-sidebar-link-icon)');
            if (label) {
                var text = (label.textContent || '').trim();
                if (text && !el.getAttribute('title')) {
                    el.setAttribute('title', text);
                }
            }
            el.setAttribute('data-jp-title-bound', '1');
        });
    }

    function bindNavCollapseLinks() {
        document.querySelectorAll('[data-jp-collapse-sidebar]').forEach(function (link) {
            link.addEventListener('click', function () {
                if (window.innerWidth >= 992) {
                    setCollapsed(true);
                }
            });
        });
    }

    function bindCollapsedSidebarWheel() {
        var nav = document.querySelector('.jp-sidebar-nav');
        var menuScroll = document.querySelector('.jp-sidebar-menu-scroll');
        if (!nav || !menuScroll) return;

        // In collapsed desktop mode the nav becomes the scroll container,
        // so forward wheel input from the menu area to keep scrolling natural.
        menuScroll.addEventListener('wheel', function (event) {
            if (!isCollapsed() || window.innerWidth < 992) return;

            var canScroll = nav.scrollHeight > nav.clientHeight;
            if (!canScroll) return;

            nav.scrollTop += event.deltaY;
            event.preventDefault();
        }, { passive: false });
    }

    document.addEventListener('DOMContentLoaded', function () {
        bindCollapseToggle();
        bindFlyouts();
        bindNavCollapseLinks();
        bindCollapsedSidebarWheel();
        applyLinkTitles();
        setCollapsed(isCollapsed());
    });
})();
