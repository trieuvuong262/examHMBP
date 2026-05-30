/**
 * Avatar — upload sidebar + phóng to trên màn hình nhân sự.
 */
(function () {
    'use strict';

    document.addEventListener('click', function (event) {
        var trigger = event.target.closest('[data-jp-avatar-trigger]');
        if (!trigger) return;
        var form = trigger.closest('form');
        var input = form && form.querySelector('[data-jp-avatar-input]');
        if (input) input.click();
    });

    document.addEventListener('change', function (event) {
        var input = event.target.closest('[data-jp-avatar-input]');
        if (!input || !input.files || !input.files.length) return;
        input.closest('form').submit();
    });

    document.addEventListener('click', function (event) {
        var btn = event.target.closest('[data-jp-avatar-zoom]');
        if (!btn) return;
        event.preventDefault();

        var url = btn.getAttribute('data-jp-avatar-zoom');
        var name = btn.getAttribute('data-jp-avatar-name') || 'Avatar';
        var modalEl = document.getElementById('jpAvatarZoomModal');
        var imgEl = document.getElementById('jpAvatarZoomImg');
        var titleEl = document.getElementById('jpAvatarZoomTitle');
        if (!url || !modalEl || !imgEl || !window.bootstrap) return;

        imgEl.src = url;
        imgEl.alt = name;
        if (titleEl) titleEl.textContent = name;

        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    });
})();
