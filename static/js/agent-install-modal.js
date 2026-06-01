(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var modalEl = document.getElementById('jpAgentInstallModal');
        if (!modalEl || typeof bootstrap === 'undefined') return;

        var modal = new bootstrap.Modal(modalEl);
        modal.show();
    });
})();
