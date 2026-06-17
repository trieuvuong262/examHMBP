/**
 * Hướng dẫn — chọn mục từ mục lục để xem nội dung (một mục tại một thời điểm) + phóng to ảnh.
 */
(function () {
    'use strict';

    var root = document.querySelector('.jp-guide-page');
    if (!root) return;

    var panels = root.querySelectorAll('[data-guide-panel]');
    var panelIds = {};
    panels.forEach(function (el) {
        panelIds[el.id] = el;
    });

    var links = root.querySelectorAll('.guide-toc-link');

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

    function showPanel(sectionId, options) {
        options = options || {};
        var target = panelIds[sectionId] || document.getElementById(sectionId);
        if (!target) return false;

        panels.forEach(function (panel) {
            panel.classList.toggle('is-active', panel.id === sectionId);
        });

        scrollToEl(target);
        setActive(sectionId);

        if (options.updateHash !== false) {
            history.replaceState(null, '', '#' + sectionId);
        }
        return true;
    }

    links.forEach(function (link) {
        link.addEventListener('click', function (e) {
            var href = link.getAttribute('href') || '';
            if (href.charAt(0) !== '#') return;
            var id = href.slice(1);
            if (!id || !panelIds[id]) return;
            e.preventDefault();
            showPanel(id);
        });
    });

    /* Phóng to ảnh minh họa */
    var modalEl = document.getElementById('guideImageModal');
    var modalImg = document.getElementById('guideLightboxImg');
    var modalCaption = document.getElementById('guideLightboxCaption');
    var imageModal = modalEl && window.bootstrap && bootstrap.Modal
        ? bootstrap.Modal.getOrCreateInstance(modalEl)
        : null;

    function openImageLightbox(img) {
        if (!imageModal || !modalImg) return;
        modalImg.src = img.currentSrc || img.src;
        modalImg.alt = img.alt || '';
        var fig = img.closest('.guide-figure, .guide-step-figure');
        var caption = fig ? fig.querySelector('figcaption') : null;
        if (modalCaption) {
            modalCaption.textContent = caption ? caption.textContent.trim() : (img.alt || '');
        }
        imageModal.show();
    }

    function bindZoomableImages(scope) {
        scope.querySelectorAll('.guide-figure img, .guide-step-figure img, .guide-zoomable').forEach(function (img) {
            if (img.dataset.guideZoomBound === '1') return;
            img.dataset.guideZoomBound = '1';
            img.classList.add('guide-zoomable');
            img.setAttribute('role', 'button');
            img.setAttribute('tabindex', '0');
            img.setAttribute('title', 'Bấm để phóng to');
            img.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                openImageLightbox(img);
            });
            img.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    e.stopPropagation();
                    openImageLightbox(img);
                }
            });
        });
    }

    bindZoomableImages(root);

    if (modalEl) {
        modalEl.addEventListener('hidden.bs.modal', function () {
            if (modalImg) modalImg.src = '';
        });
    }

    /* Hash on load / back button */
    function openFromHash() {
        var id = (window.location.hash || '').replace('#', '');
        if (id && panelIds[id]) {
            showPanel(id, { updateHash: false });
            return;
        }
        var active = root.querySelector('[data-guide-panel].is-active');
        if (active) setActive(active.id);
    }

    window.addEventListener('hashchange', openFromHash);
    openFromHash();
})();
