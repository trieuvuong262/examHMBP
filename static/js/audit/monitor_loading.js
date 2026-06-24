(function () {
    'use strict';

    function createMonitorLoading(options) {
        const root = options.root;
        const loadingEl = options.loadingEl;
        const refreshBtn = options.refreshBtn;
        let pending = 0;
        let manualActive = false;

        function syncUi() {
            const visible = pending > 0;
            const subtle = visible && !manualActive;
            if (loadingEl) {
                loadingEl.hidden = !visible;
                loadingEl.classList.toggle('is-visible', visible);
                loadingEl.classList.toggle('jp-monitor-loading--subtle', subtle);
                loadingEl.setAttribute('aria-busy', visible ? 'true' : 'false');
            }
            if (root) {
                root.classList.toggle('jp-monitor-is-loading', visible);
                root.classList.toggle('jp-monitor-is-loading--manual', visible && manualActive);
            }
            if (refreshBtn) {
                refreshBtn.disabled = manualActive;
                const icon = refreshBtn.querySelector('.bi-arrow-clockwise');
                if (icon) icon.classList.toggle('jp-spin', visible);
            }
        }

        return {
            show: function (manual) {
                pending += 1;
                if (manual) manualActive = true;
                syncUi();
            },
            hide: function () {
                pending = Math.max(0, pending - 1);
                if (pending === 0) manualActive = false;
                syncUi();
            },
        };
    }

    window.jpCreateMonitorLoading = createMonitorLoading;
})();
