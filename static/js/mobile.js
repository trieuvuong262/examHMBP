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
        var drawer = document.getElementById('mobileMenu');
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

    function bindNavClose() {
        document.querySelectorAll('#mobileMenu a.nav-link, #mobileMenu .dropdown-item').forEach(function (link) {
            link.addEventListener('click', closeMobileMenu);
        });
    }

    function setBottomNavActive() {
        var path = window.location.pathname;
        document.querySelectorAll('.jp-bottom-nav a[data-nav]').forEach(function (a) {
            var match = a.getAttribute('data-nav');
            if (!match) return;
            if (match === '/' && path === '/') {
                a.classList.add('active');
            } else if (match !== '/' && path.indexOf(match) === 0) {
                a.classList.add('active');
            }
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        enhanceTables();
        bindNavClose();
        setBottomNavActive();
    });
})();
