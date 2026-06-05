(function () {
    function initKvSyncPoll() {
        const card = document.getElementById('jp-kv-sync-progress-card');
        if (!card || !card.dataset.statusUrl) return;

        const statusUrl = card.dataset.statusUrl;
        const bar = document.getElementById('jp-kv-sync-progress-bar');
        const pctBadge = document.getElementById('jp-kv-sync-percent');
        const statusLabel = document.getElementById('jp-kv-sync-status-label');
        const statusIcon = document.getElementById('jp-kv-sync-status-icon');
        const entityStepEl = document.getElementById('jp-kv-sync-entity-step');
        const messageEl = document.getElementById('jp-kv-sync-message');
        const doneActions = document.getElementById('jp-kv-sync-done-actions');

        if (!bar || !pctBadge || !statusLabel || !messageEl) return;

        card.hidden = false;

        function applyStatus(data) {
            const pct = Math.max(0, Math.min(100, data.progress_percent || 0));
            bar.style.width = pct + '%';
            bar.setAttribute('aria-valuenow', String(pct));
            bar.textContent = pct + '%';
            pctBadge.textContent = pct + '%';

            if (data.is_active) {
                statusLabel.textContent = 'Đang đồng bộ'
                    + (data.current_entity_label ? ': ' + data.current_entity_label : '…');
                if (statusIcon) {
                    statusIcon.className = 'bi bi-hourglass-split text-hm me-1';
                }
                bar.classList.add('progress-bar-animated', 'progress-bar-striped', 'bg-hm');
                bar.classList.remove('bg-success', 'bg-danger');
                if (doneActions) doneActions.classList.add('d-none');
            } else {
                statusLabel.textContent = data.status_display || 'Hoàn tất';
                if (statusIcon) {
                    if (data.status === 'success') {
                        statusIcon.className = 'bi bi-check-circle-fill text-success me-1';
                    } else if (data.status === 'failed') {
                        statusIcon.className = 'bi bi-x-circle-fill text-danger me-1';
                    } else {
                        statusIcon.className = 'bi bi-flag-fill text-hm me-1';
                    }
                }
                bar.classList.remove('progress-bar-animated', 'progress-bar-striped', 'bg-hm');
                if (data.status === 'success') {
                    bar.classList.add('bg-success');
                } else if (data.status === 'failed') {
                    bar.classList.add('bg-danger');
                }
                if (doneActions) doneActions.classList.remove('d-none');
            }

            if (entityStepEl) {
                if (data.entity_total > 0) {
                    const idx = data.entity_index || 0;
                    entityStepEl.textContent = data.is_active
                        ? ('Mục ' + idx + '/' + data.entity_total
                            + (data.rows_synced ? ' · Đã ghi ' + data.rows_synced + ' bản ghi' : ''))
                        : ('Hoàn tất ' + data.entity_total + '/' + data.entity_total + ' mục'
                            + (data.rows_synced ? ' · ' + data.rows_synced + ' bản ghi' : '')
                            + (data.duration_display && data.duration_display !== '—'
                                ? ' · ' + data.duration_display : ''));
                } else {
                    entityStepEl.textContent = '';
                }
            }

            let msg = data.message || '';
            if (!data.is_active && data.status === 'success') {
                msg = msg || 'Đồng bộ hoàn tất 100%.';
            }
            messageEl.textContent = msg;
        }

        function poll() {
            fetch(statusUrl, {
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin',
            })
                .then(function (r) {
                    if (!r.ok) throw new Error('status ' + r.status);
                    return r.json();
                })
                .then(function (data) {
                    applyStatus(data);
                    if (data.is_active) {
                        window.setTimeout(poll, 1000);
                    }
                })
                .catch(function () {
                    messageEl.textContent = 'Đang kết nối lại để cập nhật tiến độ…';
                    window.setTimeout(poll, 2000);
                });
        }

        poll();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initKvSyncPoll);
    } else {
        initKvSyncPoll();
    }
})();
