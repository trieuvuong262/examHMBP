/**
 * Sidebar — chọn ảnh avatar và gửi form upload.
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
})();
