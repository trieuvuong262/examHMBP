(function () {
    'use strict';

    function createMonitorLoading(options) {
        const loadingEl = options.loadingEl;
        const refreshBtn = options.refreshBtn;
        let initialPending = 0;
        let buttonPending = 0;
        let initialDone = false;

        function syncInitial() {
            const visible = initialPending > 0 && !initialDone;
            if (loadingEl) {
                loadingEl.hidden = !visible;
                loadingEl.classList.toggle('is-visible', visible);
                loadingEl.classList.toggle('jp-monitor-loading--subtle', visible);
                loadingEl.setAttribute('aria-busy', visible ? 'true' : 'false');
            }
        }

        function syncButton() {
            if (!refreshBtn) return;
            const busy = buttonPending > 0;
            refreshBtn.disabled = busy;
            const icon = refreshBtn.querySelector('.bi-arrow-clockwise');
            if (icon) icon.classList.toggle('jp-spin', busy);
        }

        return {
            /** Overlay nhẹ — chỉ lần đầu vào trang, không chặn thao tác. */
            showInitial: function () {
                if (initialDone) return;
                initialPending += 1;
                syncInitial();
            },
            hideInitial: function () {
                initialPending = Math.max(0, initialPending - 1);
                if (initialPending === 0) {
                    initialDone = true;
                }
                syncInitial();
            },
            /** Chỉ quay icon nút Làm mới. */
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
