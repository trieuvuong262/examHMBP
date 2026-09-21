/**
 * Avatar — upload sidebar + phóng to trên màn hình nhân sự.
 */
(function () {
    'use strict';

    document.addEventListener('click', function (event) {
        var trigger = event.target.closest('[data-jp-avatar-trigger]');
        if (!trigger) return;
        var form = trigger.closest('form');
        if (!form) {
            form = document.querySelector('.jp-topbar-avatar-form, .jp-sidebar-avatar-form');
        }
        var input = form && form.querySelector('[data-jp-avatar-input]');
        if (input) input.click();
    });

    document.addEventListener('change', function (event) {
        var input = event.target.closest('[data-jp-avatar-input]');
        if (!input || !input.files || !input.files.length) return;
        input.closest('form').submit();
    });

    function liftOverlay(modalEl) {
        modalEl.style.zIndex = '1120';
        document.querySelectorAll('.modal-backdrop').forEach(function (bd) {
            bd.style.zIndex = '1110';
        });
    }

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-jp-avatar-zoom]');
        if (!btn) return;
        event.preventDefault();
        event.stopPropagation();

        var url = btn.getAttribute('data-jp-avatar-zoom');
        var name = btn.getAttribute('data-jp-avatar-name') || 'Avatar';
        var modalEl = document.getElementById('jpAvatarZoomModal');
        var imgEl = document.getElementById('jpAvatarZoomImg');
        var titleEl = document.getElementById('jpAvatarZoomTitle');
        if (!url || !modalEl || !imgEl || !window.bootstrap) return;

        imgEl.src = url;
        imgEl.alt = name;
        if (titleEl) titleEl.textContent = name;

        if (modalEl.parentNode !== document.body) {
            document.body.appendChild(modalEl);
        }
        liftOverlay(modalEl);
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
        window.requestAnimationFrame(function () {
            liftOverlay(modalEl);
        });
    });
})();
