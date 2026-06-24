(function () {
    'use strict';

    const root = document.getElementById('jp-vps-monitor');
    if (!root) return;

    const metricsUrl = root.dataset.metricsUrl;
    const refreshSec = parseInt(root.dataset.autoRefresh || '30', 10);
    const refreshBtn = document.getElementById('jp-vps-refresh');
    const updatedEl = document.getElementById('jp-vps-updated');

    function formatBytes(bytes) {
        if (bytes == null || Number.isNaN(bytes)) return '—';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        let n = Number(bytes);
        let i = 0;
        while (n >= 1024 && i < units.length - 1) {
            n /= 1024;
            i += 1;
        }
        return (i === 0 ? String(Math.round(n)) : n.toFixed(1)) + ' ' + units[i];
    }

    function setBar(el, pct) {
        if (!el) return;
        const value = Math.max(0, Math.min(100, Number(pct) || 0));
        el.style.width = value + '%';
    }

    function renderContainers(rows) {
        const tbody = document.getElementById('jp-vps-containers');
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="3" class="text-muted small p-3">Chưa có dữ liệu container.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (row) {
            const pct = row.memory_percent != null ? row.memory_percent + '%' : '—';
            return '<tr><td class="font-monospace small">' + row.name + '</td><td>' + row.memory_display + '</td><td class="text-end">' + pct + '</td></tr>';
        }).join('');
    }

    function applyMetrics(metrics) {
        const ram = metrics.ram || {};
        const cpu = metrics.cpu || {};
        const disk = metrics.disk || {};
        const summary = (metrics.docker && metrics.docker.summary) || {};

        const ramDisplay = document.querySelector('[data-jp-vps-ram-display]');
        if (ramDisplay) ramDisplay.textContent = ram.display || formatBytes(ram.used_bytes) + ' / ' + formatBytes(ram.total_bytes);
        setBar(document.querySelector('[data-jp-vps-ram-bar]'), ram.used_percent);
        const ramPct = document.querySelector('[data-jp-vps-ram-pct]');
        if (ramPct) ramPct.textContent = (ram.used_percent != null ? ram.used_percent : '—') + (ram.used_percent != null ? '%' : '');

        const cpuDisplay = document.querySelector('[data-jp-vps-cpu-display]');
        if (cpuDisplay) cpuDisplay.textContent = cpu.percent != null ? cpu.percent + '%' : '—';
        setBar(document.querySelector('[data-jp-vps-cpu-bar]'), cpu.percent);
        const loadEl = document.querySelector('[data-jp-vps-load]');
        if (loadEl && cpu.loadavg) loadEl.textContent = cpu.loadavg['1m'];

        const diskDisplay = document.querySelector('[data-jp-vps-disk-display]');
        if (diskDisplay && disk.used_bytes != null) {
            diskDisplay.textContent = formatBytes(disk.used_bytes) + ' / ' + formatBytes(disk.total_bytes);
        }
        setBar(document.querySelector('[data-jp-vps-disk-bar]'), disk.used_percent);
        const diskPct = document.querySelector('[data-jp-vps-disk-pct]');
        if (diskPct) diskPct.textContent = (disk.used_percent != null ? disk.used_percent : '—') + (disk.used_percent != null ? '%' : '');

        renderContainers((metrics.docker && metrics.docker.containers) || []);

        const imagesEl = document.querySelector('[data-jp-vps-images]');
        if (imagesEl) imagesEl.textContent = formatBytes(summary.images_bytes);
        const imagesReclaim = document.querySelector('[data-jp-vps-images-reclaim]');
        if (imagesReclaim) imagesReclaim.textContent = formatBytes(summary.images_reclaimable_bytes);
        const volumesEl = document.querySelector('[data-jp-vps-volumes]');
        if (volumesEl) volumesEl.textContent = formatBytes(summary.volumes_bytes);
        const containerdEl = document.querySelector('[data-jp-vps-containerd]');
        if (containerdEl) containerdEl.textContent = formatBytes(summary.containerd_bytes);

        if (updatedEl) {
            const now = new Date();
            updatedEl.textContent = 'Cập nhật ' + now.toLocaleTimeString('vi-VN');
        }
    }

    async function refreshMetrics() {
        if (!metricsUrl) return;
        try {
            const resp = await fetch(metricsUrl, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            const data = await resp.json();
            if (data.status === 'success' && data.metrics) {
                applyMetrics(data.metrics);
            }
        } catch (err) {
            console.warn('VPS metrics refresh failed', err);
        }
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            refreshMetrics();
        });
    }

    if (updatedEl) {
        const now = new Date();
        updatedEl.textContent = 'Cập nhật ' + now.toLocaleTimeString('vi-VN');
    }

    if (refreshSec > 0) {
        setInterval(refreshMetrics, refreshSec * 1000);
    }
})();
