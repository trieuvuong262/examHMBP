/**
 * JustPlay mobile enhancements — auto-applied on all pages.
 */
(function () {
    'use strict';

    function enhanceTables() {
        document.querySelectorAll('main table').forEach(function (table) {
            if (table.dataset.jpEnhanced || table.closest('#lines-table')) return;
            table.dataset.jpEnhanced = '1';

            var wrap = table.closest('.table-responsive');
            if (wrap) {
                wrap.classList.add('jp-table-wrap');
            }
            table.classList.add('jp-table');

            if (table.classList.contains('table-kpi') || table.closest('.table-kpi-wrap')) {
                if (wrap) wrap.classList.add('jp-kpi-scroll', 'jp-table-scroll');
                return;
            }

            var headers = [];
            table.querySelectorAll('thead th').forEach(function (th, i) {
                headers[i] = (th.textContent || '').trim();
            });
            if (!headers.length) return;

            table.classList.add('jp-table-stack');
            table.querySelectorAll('tbody tr').forEach(function (row) {
                row.querySelectorAll('td').forEach(function (td, i) {
                    if (!td.getAttribute('data-label') && headers[i]) {
                        td.setAttribute('data-label', headers[i]);
                    }
                    if (td.querySelector('.btn') && td.cellIndex === row.cells.length - 1) {
                        td.classList.add('jp-td-actions');
                    }
                });
            });
        });
    }

    function closeMobileMenu() {
        var drawer = document.getElementById('mobileSidebar') || document.getElementById('mobileMenu');
        if (drawer && window.bootstrap) {
            var instance = bootstrap.Offcanvas.getInstance(drawer);
            if (instance) instance.hide();
        }
        var collapse = document.getElementById('mainNavbar');
        if (collapse && window.bootstrap) {
            var col = bootstrap.Collapse.getInstance(collapse);
            if (col) col.hide();
        }
    }

    function bindSidebarGroups() {
        document.querySelectorAll('[data-jp-sidebar-group-toggle]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (document.documentElement.classList.contains('jp-sidebar-collapsed') && window.innerWidth >= 992) {
                    return;
                }
                var group = btn.closest('.jp-sidebar-group, .jp-sidebar-nested-group');
                if (!group) return;
                var open = group.classList.toggle('is-open');
                btn.setAttribute('aria-expanded', open ? 'true' : 'false');
            });
        });
    }

    function bindNavClose() {
        document.querySelectorAll('#mobileSidebar a.jp-sidebar-link, #mobileMenu a.nav-link, #mobileMenu .dropdown-item').forEach(function (link) {
            link.addEventListener('click', closeMobileMenu);
        });
    }

    function setBottomNavActive() {
        var path = window.location.pathname;
        document.querySelectorAll('.jp-bottom-nav a[data-nav]').forEach(function (a) {
            a.classList.remove('active');
            var match = a.getAttribute('data-nav');
            if (!match) return;
            if (match === '/') {
                if (path === '/' || path === '') {
                    a.classList.add('active');
                }
            } else if (path.indexOf(match) === 0) {
                a.classList.add('active');
            }
        });
    }

    function enhanceLongText() {
        var clampSelectors = [
            '.jp-text-clamp-1',
            '.jp-text-clamp-2',
            '.jp-text-clamp-3',
            '.jp-text-clamp',
            '.jp-text-truncate',
            '.course-title',
            '.exam-title',
            '.card-title',
            'main .card-body h5.fw-bold',
            'main table td .fw-bold.text-dark',
            'main table td h6.fw-bold',
            '.jp-dashboard-item-title',
            '.jp-dashboard-item-text',
            '.kanban-card h6.fw-bold',
            '.kanban-card p.text-hm',
            '.portal-card h5'
        ];

        document.querySelectorAll(clampSelectors.join(',')).forEach(function (el) {
            if (el.getAttribute('title')) return;
            var text = (el.textContent || '').replace(/\s+/g, ' ').trim();
            if (!text) return;
            if (el.scrollHeight > el.clientHeight + 2 || el.scrollWidth > el.clientWidth + 2) {
                el.setAttribute('title', text);
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        enhanceTables();
        enhanceLongText();
        bindSidebarGroups();
        bindNavClose();
        setBottomNavActive();
    });
})();
