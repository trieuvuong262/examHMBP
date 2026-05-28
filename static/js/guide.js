/**
 * Hướng dẫn — mở accordion + cuộn tới mục khi bấm mục lục / hash URL.
 */
(function () {
    'use strict';

    var root = document.querySelector('.jp-guide-page');
    if (!root) return;

    var links = root.querySelectorAll('.guide-toc-link, .guide-preview-item, a[href^="#"]');
    var sectionIds = {};
    root.querySelectorAll('.accordion-item[id]').forEach(function (el) {
        sectionIds[el.id] = el;
    });

    function getScrollOffset() {
        var nav = document.querySelector('.navbar.sticky-top');
        var navH = nav ? nav.offsetHeight : 56;
        var mobileToc = root.querySelector('.guide-mobile-toc');
        var tocH = 0;
        if (mobileToc && window.matchMedia('(max-width: 991.98px)').matches) {
            tocH = mobileToc.offsetHeight + 8;
        }
        return navH + tocH + 12;
    }

    function setActive(id) {
        root.querySelectorAll('.guide-toc-link').forEach(function (a) {
            var href = a.getAttribute('href') || '';
            a.classList.toggle('active', href === '#' + id);
        });
    }

    function scrollToEl(el) {
        if (!el) return;
        var top = el.getBoundingClientRect().top + window.scrollY - getScrollOffset();
        window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' });
    }

    function openSection(sectionId, options) {
        options = options || {};
        var item = sectionIds[sectionId] || document.getElementById(sectionId);
        if (!item) return false;

        var panel = item.classList.contains('accordion-item')
            ? item.querySelector('.accordion-collapse')
            : null;

        function finish() {
            scrollToEl(item);
            setActive(sectionId);
            if (options.updateHash !== false) {
                history.replaceState(null, '', '#' + sectionId);
            }
        }

        if (!panel || panel.classList.contains('show')) {
            finish();
            return true;
        }

        if (!window.bootstrap || !bootstrap.Collapse) {
            panel.classList.add('show');
            finish();
            return true;
        }

        var inst = bootstrap.Collapse.getOrCreateInstance(panel, { toggle: false });
        panel.addEventListener('shown.bs.collapse', function onShown() {
            panel.removeEventListener('shown.bs.collapse', onShown);
            finish();
        });
        inst.show();
        return true;
    }

    function handleJump(event, link) {
        var href = link.getAttribute('href') || '';
        if (href.charAt(0) !== '#') return;
        var id = href.slice(1);
        if (!id || !sectionIds[id]) return;

        event.preventDefault();
        openSection(id);
    }

    links.forEach(function (link) {
        link.addEventListener('click', function (e) {
            handleJump(e, link);
        });
    });

    /* Highlight section while scrolling */
    var sections = root.querySelectorAll('.accordion-item[id]');
    if ('IntersectionObserver' in window && sections.length) {
        var observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                if (entry.isIntersecting) setActive(entry.target.id);
            });
        }, { rootMargin: '-25% 0px -50% 0px', threshold: 0 });
        sections.forEach(function (el) { observer.observe(el); });
    }

    /* Hash on load / back button */
    function openFromHash() {
        var id = (window.location.hash || '').replace('#', '');
        if (id && sectionIds[id]) {
            setTimeout(function () { openSection(id, { updateHash: false }); }, 80);
        }
    }

    window.addEventListener('hashchange', openFromHash);
    openFromHash();
})();
