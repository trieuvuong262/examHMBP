(function () {
    'use strict';

    function createMonitorLoading(options) {
        const loadingEl = options.loadingEl;
        const refreshBtn = options.refreshBtn;
        let initialPending = 0;
        let buttonPending = 0;
        let tabPending = 0;
        let initialDone = false;

        function syncOverlay() {
            const visible = (initialPending > 0 && !initialDone) || tabPending > 0;
            if (loadingEl) {
                loadingEl.hidden = !visible;
                loadingEl.classList.toggle('is-visible', visible);
                loadingEl.setAttribute('aria-busy', visible ? 'true' : 'false');
            }
            document.body.classList.toggle('jp-monitor-modal-open', visible);
        }

        function syncButton() {
            if (!refreshBtn) return;
            const busy = buttonPending > 0;
            refreshBtn.disabled = busy;
            const icon = refreshBtn.querySelector('.bi-arrow-clockwise');
            if (icon) icon.classList.toggle('jp-spin', busy);
        }

        return {
            showInitial: function () {
                if (initialDone) return;
                initialPending += 1;
                syncOverlay();
            },
            hideInitial: function () {
                initialPending = Math.max(0, initialPending - 1);
                if (initialPending === 0) {
                    initialDone = true;
                }
                syncOverlay();
            },
            showTab: function () {
                tabPending += 1;
                syncOverlay();
            },
            hideTab: function () {
                tabPending = Math.max(0, tabPending - 1);
                syncOverlay();
            },
            showButtonBusy: function () {
                buttonPending += 1;
                syncButton();
            },
            hideButtonBusy: function () {
                buttonPending = Math.max(0, buttonPending - 1);
                syncButton();
            },
        };
    }

    window.jpCreateMonitorLoading = createMonitorLoading;
})();
