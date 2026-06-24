(function () {
    'use strict';

    const root = document.getElementById('jp-nas-monitor');
    if (!root) return;

    const metricsUrl = root.dataset.metricsUrl;
    const refreshSec = parseInt(root.dataset.autoRefresh || '30', 10);
    const performanceRefreshSec = parseInt(root.dataset.performanceRefresh || '5', 10);
    const refreshBtn = document.getElementById('jp-nas-refresh');
    const updatedEl = document.getElementById('jp-nas-updated');
    const loadingEl = document.getElementById('jp-nas-loading');
    const performanceTab = document.getElementById('jp-nas-tab-performance');
    const performanceTabBtn = document.getElementById('jp-nas-tab-performance-btn');

    const loading = window.jpCreateMonitorLoading
        ? window.jpCreateMonitorLoading({ loadingEl: loadingEl, refreshBtn: refreshBtn })
        : { showInitial: function () {}, hideInitial: function () {}, showButtonBusy: function () {}, hideButtonBusy: function () {} };

    const HISTORY_MAX = 60;
    const chartHistory = { labels: [], cpu: [], ram: [], disk: [] };
    let performanceCharts = null;
    let refreshTimer = null;
    let performanceTabActive = false;

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

    function escapeHtml(text) {
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function setBar(el, pct) {
        if (!el) return;
        const value = Math.max(0, Math.min(100, Number(pct) || 0));
        el.style.width = value + '%';
    }

    function formatTimeLabel(date) {
        return date.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function pushChartHistory(metrics) {
        const ram = metrics.ram || {};
        const cpu = metrics.cpu || {};
        const disk = metrics.disk || {};
        const now = new Date();

        chartHistory.labels.push(formatTimeLabel(now));
        chartHistory.cpu.push(cpu.percent != null ? Number(cpu.percent) : null);
        chartHistory.ram.push(ram.used_percent != null ? Number(ram.used_percent) : null);
        chartHistory.disk.push(disk.used_percent != null ? Number(disk.used_percent) : null);

        if (chartHistory.labels.length > HISTORY_MAX) {
            chartHistory.labels.shift();
            chartHistory.cpu.shift();
            chartHistory.ram.shift();
            chartHistory.disk.shift();
        }
    }

    function chartOptions() {
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            scales: {
                x: { ticks: { maxTicksLimit: 6, maxRotation: 0 } },
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { callback: function (v) { return v + '%'; } },
                },
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (ctx) {
                            const v = ctx.parsed.y;
                            return v != null ? v.toFixed(1) + '%' : '—';
                        },
                    },
                },
            },
            elements: { point: { radius: 0, hitRadius: 8, hoverRadius: 3 } },
        };
    }

    function initPerformanceCharts() {
        if (performanceCharts || typeof Chart === 'undefined') return;

        const lineDataset = function (label, color, bg) {
            return {
                label: label,
                data: [],
                borderColor: color,
                backgroundColor: bg,
                borderWidth: 2,
                fill: true,
                tension: 0.25,
                spanGaps: true,
            };
        };

        performanceCharts = {
            cpu: new Chart(document.getElementById('jp-nas-chart-cpu'), {
                type: 'line',
                data: { labels: chartHistory.labels, datasets: [lineDataset('CPU', '#16a34a', 'rgba(22, 163, 74, 0.12)')] },
                options: chartOptions(),
            }),
            ram: new Chart(document.getElementById('jp-nas-chart-ram'), {
                type: 'line',
                data: { labels: chartHistory.labels, datasets: [lineDataset('RAM', '#2563eb', 'rgba(37, 99, 235, 0.12)')] },
                options: chartOptions(),
            }),
            disk: new Chart(document.getElementById('jp-nas-chart-disk'), {
                type: 'line',
                data: { labels: chartHistory.labels, datasets: [lineDataset('Ổ đĩa', '#d97706', 'rgba(217, 119, 6, 0.12)')] },
                options: chartOptions(),
            }),
        };
    }

    function updatePerformanceCharts() {
        if (!performanceCharts) return;
        ['cpu', 'ram', 'disk'].forEach(function (key) {
            const historyKey = key;
            performanceCharts[key].data.labels = chartHistory.labels;
            performanceCharts[key].data.datasets[0].data = chartHistory[historyKey].slice();
            performanceCharts[key].update('none');
        });
    }

    function renderShares(rows, tbodyId) {
        const tbody = document.getElementById(tbodyId);
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted small p-3">Chưa có dữ liệu share.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (row) {
            const pct = row.used_percent != null ? row.used_percent + '%' : '—';
            const size = row.size_display || row.used_display || (row.used_bytes != null ? formatBytes(row.used_bytes) : '—');
            const quota = row.quota_display || (row.total_bytes != null ? formatBytes(row.total_bytes) : '—');
            const free = row.free_display || (row.free_bytes != null ? formatBytes(row.free_bytes) : '—');
            return (
                '<tr>' +
                '<td class="font-monospace small">' + escapeHtml(row.name) + '</td>' +
                '<td class="text-end">' + escapeHtml(size) + '</td>' +
                '<td class="text-end">' + escapeHtml(quota) + '</td>' +
                '<td class="text-end">' + escapeHtml(free) + '</td>' +
                '<td class="text-end">' + pct + '</td>' +
                '</tr>'
            );
        }).join('');
    }

    function renderVolumes(rows) {
        const tbody = document.getElementById('jp-nas-volumes');
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted small p-3">Chưa có dữ liệu volume (cần DSM API).</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (vol) {
            const pct = vol.used_percent != null ? vol.used_percent + '%' : '—';
            return (
                '<tr>' +
                '<td class="font-monospace small">' + escapeHtml(vol.name) + '</td>' +
                '<td class="small">' + escapeHtml(vol.status) + '</td>' +
                '<td class="text-end">' + escapeHtml(vol.display) + '</td>' +
                '<td class="text-end">' + pct + '</td>' +
                '</tr>'
            );
        }).join('');
    }

    function renderProcesses(rows) {
        const tbody = document.getElementById('jp-nas-processes');
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted small p-3">Chưa có dữ liệu tiến trình (cần cấu hình DSM API).</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(function (proc) {
            const cpu = proc.cpu_percent != null ? proc.cpu_percent + '%' : '—';
            const memPct = proc.memory_percent != null ? proc.memory_percent + '%' : '—';
            return (
                '<tr>' +
                '<td class="font-monospace small">' + escapeHtml(proc.name) + '</td>' +
                '<td class="text-end font-monospace small">' + escapeHtml(proc.pid) + '</td>' +
                '<td class="text-end">' + cpu + '</td>' +
                '<td class="text-end">' + formatBytes(proc.memory_bytes) + '</td>' +
                '<td class="text-end">' + memPct + '</td>' +
                '</tr>'
            );
        }).join('');
    }

    function applyPerformanceMetrics(metrics) {
        const ram = metrics.ram || {};
        const cpu = metrics.cpu || {};
        const disk = metrics.disk || {};

        const perfCpu = document.querySelector('[data-jp-nas-perf-cpu]');
        if (perfCpu) perfCpu.textContent = cpu.percent != null ? cpu.percent + '%' : '—';

        const perfRam = document.querySelector('[data-jp-nas-perf-ram]');
        if (perfRam) perfRam.textContent = ram.used_percent != null ? ram.used_percent + '%' : '—';
        const perfRamDetail = document.querySelector('[data-jp-nas-perf-ram-detail]');
        if (perfRamDetail) perfRamDetail.textContent = ram.display || '—';

        const perfDisk = document.querySelector('[data-jp-nas-perf-disk]');
        if (perfDisk) perfDisk.textContent = disk.used_percent != null ? disk.used_percent + '%' : '—';
        const perfDiskDetail = document.querySelector('[data-jp-nas-perf-disk-detail]');
        if (perfDiskDetail) perfDiskDetail.textContent = disk.display || '—';

        renderProcesses(metrics.processes || []);

        if (performanceTabActive) {
            pushChartHistory(metrics);
            if (!performanceCharts) initPerformanceCharts();
            updatePerformanceCharts();
        }
    }

    function renderWidgets(widgets, metrics) {
        const health = widgets.system_health || {};
        const sys = widgets.system_info || {};
        const res = widgets.resource || {};
        const storage = widgets.storage || {};

        const healthStatus = document.querySelector('[data-jp-nas-health-status]');
        if (healthStatus) healthStatus.textContent = health.status || '—';
        const healthSummary = document.querySelector('[data-jp-nas-health-summary]');
        if (healthSummary) healthSummary.textContent = health.summary || '';
        const healthTemp = document.querySelector('[data-jp-nas-health-temp]');
        if (healthTemp) {
            healthTemp.textContent = health.temperature != null && health.temperature !== ''
                ? health.temperature + '°C' : '—';
        }

        const sysHost = document.querySelector('[data-jp-nas-sys-hostname]');
        if (sysHost) sysHost.textContent = sys.hostname || (metrics && metrics.hostname) || '—';
        const sysUptime = document.querySelector('[data-jp-nas-sys-uptime]');
        if (sysUptime) sysUptime.textContent = sys.uptime_display || '—';

        const resCpu = document.querySelector('[data-jp-nas-res-cpu]');
        if (resCpu) {
            const pct = res.cpu_percent != null ? res.cpu_percent : (metrics && metrics.cpu && metrics.cpu.percent);
            resCpu.textContent = pct != null ? pct + '%' : '—';
        }
        const resRamPct = document.querySelector('[data-jp-nas-res-ram-pct]');
        if (resRamPct) {
            const ram = res.ram || (metrics && metrics.ram) || {};
            resRamPct.textContent = ram.used_percent != null ? ram.used_percent + '%' : '—';
        }
        const resRamDisplay = document.querySelector('[data-jp-nas-res-ram-display]');
        if (resRamDisplay) {
            const ram = res.ram || (metrics && metrics.ram) || {};
            resRamDisplay.textContent = ram.display || '—';
        }
        const resSwap = document.querySelector('[data-jp-nas-res-swap]');
        if (resSwap) resSwap.textContent = (res.swap && res.swap.display) || '—';

        const usersCount = document.querySelector('[data-jp-nas-users-count]');
        if (usersCount) usersCount.textContent = String((widgets.connected_users || []).length);

        function fillTable(tbodyId, rows, emptyHtml, renderRow) {
            const tbody = document.getElementById(tbodyId);
            if (!tbody) return;
            if (!rows || !rows.length) {
                tbody.innerHTML = emptyHtml;
                return;
            }
            tbody.innerHTML = rows.map(renderRow).join('');
        }

        fillTable(
            'jp-nas-widget-health-items',
            health.items,
            '<tr><td colspan="2" class="text-muted small p-2">—</td></tr>',
            function (row) {
                const detail = row.detail ? ' — ' + escapeHtml(row.detail) : '';
                return '<tr><td class="small">' + escapeHtml(row.title) + '</td><td class="small">' +
                    escapeHtml(row.status) + detail + '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-health-disks',
            health.disks,
            '<tr><td colspan="4" class="text-muted small p-2">—</td></tr>',
            function (row) {
                return '<tr><td class="small">' + escapeHtml(row.slot) + '</td><td class="small">' +
                    escapeHtml(row.model) + '</td><td class="small">' + escapeHtml(row.status) +
                    '</td><td class="small text-end">' + escapeHtml(String(row.temperature != null ? row.temperature : '—')) +
                    '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-network',
            res.network,
            '<tr><td colspan="3" class="text-muted small p-2">—</td></tr>',
            function (row) {
                return '<tr><td class="small">' + escapeHtml(row.device) + '</td><td class="small text-end">' +
                    escapeHtml(row.rx_display || '—') + '</td><td class="small text-end">' +
                    escapeHtml(row.tx_display || '—') + '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-users',
            widgets.connected_users,
            '<tr><td colspan="4" class="text-muted small p-3">Không có phiên đăng nhập.</td></tr>',
            function (row) {
                return '<tr><td class="small">' + escapeHtml(row.user) + '</td><td class="small font-monospace">' +
                    escapeHtml(row.ip) + '</td><td class="small">' + escapeHtml(row.protocol) +
                    '</td><td class="small text-nowrap">' + escapeHtml(row.time) + '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-tasks',
            widgets.scheduled_tasks,
            '<tr><td colspan="5" class="text-muted small p-3">Không có tác vụ hoặc thiếu quyền DSM.</td></tr>',
            function (row) {
                const enabled = row.enabled === true ? 'Có' : (row.enabled === false ? 'Không' : '—');
                const last = row.last + (row.last_result && row.last_result !== '—' ? ' (' + row.last_result + ')' : '');
                return '<tr><td class="small">' + escapeHtml(row.name) + '</td><td class="small">' +
                    escapeHtml(row.type) + '</td><td class="small">' + enabled +
                    '</td><td class="small text-nowrap">' + escapeHtml(row.next) +
                    '</td><td class="small text-nowrap">' + escapeHtml(last) + '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-logs',
            widgets.recent_logs,
            '<tr><td colspan="4" class="text-muted small p-3">Chưa lấy được log (cần Log Center / quyền admin).</td></tr>',
            function (row) {
                const msg = (row.user ? '<span class="text-muted">' + escapeHtml(row.user) + ':</span> ' : '') +
                    escapeHtml(row.message);
                return '<tr><td class="small text-nowrap">' + escapeHtml(row.time) + '</td><td class="small">' +
                    escapeHtml(row.level) + '</td><td class="small">' + escapeHtml(row.source) +
                    '</td><td class="small">' + msg + '</td></tr>';
            }
        );

        const backupRows = widgets.backup_tasks || [];
        const backup = (metrics && metrics.backup) || widgets.portal_backup || {};
        fillTable(
            'jp-nas-widget-backup',
            backupRows,
            '<tr><td colspan="5" class="small p-3 text-muted">Không có Hyper Backup / Active Backup. Portal backup: <code>' +
                escapeHtml(backup.remote || '—') + '</code>' +
                (backup.display ? ' — ' + escapeHtml(backup.display) : '') + '</td></tr>',
            function (row) {
                return '<tr><td class="small">' + escapeHtml(row.name) + '</td><td class="small">' +
                    escapeHtml(row.type || '—') + '</td><td class="small">' + escapeHtml(row.status) +
                    '</td><td class="small text-nowrap">' + escapeHtml(row.last) +
                    '</td><td class="small">' + escapeHtml(row.destination || '—') + '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-changes',
            widgets.file_changes,
            '<tr><td colspan="5" class="text-muted small p-3">Chưa lấy được nhật ký thay đổi file.</td></tr>',
            function (row) {
                return '<tr><td class="small text-nowrap">' + escapeHtml(row.time) + '</td><td class="small">' +
                    escapeHtml(row.user) + '</td><td class="small font-monospace">' + escapeHtml(row.ip || '—') +
                    '</td><td class="small font-monospace">' + escapeHtml(row.path) +
                    '</td><td class="small">' + escapeHtml(row.action) + '</td></tr>';
            }
        );

        const volRows = storage.volumes || (metrics && metrics.volumes) || [];
        fillTable(
            'jp-nas-widget-volumes',
            volRows.slice(0, 8),
            '<tr><td colspan="4" class="text-muted p-3">—</td></tr>',
            function (vol) {
                const pct = vol.used_percent != null ? vol.used_percent + '%' : '—';
                return '<tr><td>' + escapeHtml(vol.name) + '</td><td class="small">' +
                    escapeHtml(vol.status || '—') + '</td><td class="text-end">' + pct +
                    '</td><td class="text-end small">' + escapeHtml(vol.display || '—') + '</td></tr>';
            }
        );

        fillTable(
            'jp-nas-widget-shares-mini',
            (storage.shares || []).slice(0, 6),
            '',
            function (share) {
                return '<tr><td>' + escapeHtml(share.name) + '</td><td class="text-end small">' +
                    escapeHtml(share.size_display || share.used_display || '—') + '</td><td class="text-end small">' +
                    escapeHtml(share.quota_display || '—') + '</td></tr>';
            }
        );
    }

    const overviewTabBtn = document.getElementById('jp-nas-tab-overview-btn');
    const dsmTabBtn = document.getElementById('jp-nas-tab-dsm-btn');

    let activeScope = 'overview';

    function setActiveScope(scope) {
        activeScope = scope || 'overview';
    }

    function applyMetricsForScope(metrics, scope) {
        if (scope === 'performance') {
            applyPerformanceMetrics(metrics);
        } else if (scope === 'full') {
            applyMetrics(metrics);
        } else {
            const ram = metrics.ram || {};
            const cpu = metrics.cpu || {};
            const disk = metrics.disk || {};
            const backup = metrics.backup || {};

            const ramDisplay = document.querySelector('[data-jp-nas-ram-display]');
            if (ramDisplay) ramDisplay.textContent = ram.display || '—';
            setBar(document.querySelector('[data-jp-nas-ram-bar]'), ram.used_percent);
            const ramPct = document.querySelector('[data-jp-nas-ram-pct]');
            if (ramPct) ramPct.textContent = (ram.used_percent != null ? ram.used_percent : '—') + (ram.used_percent != null ? '%' : '');

            const cpuDisplay = document.querySelector('[data-jp-nas-cpu-display]');
            if (cpuDisplay) cpuDisplay.textContent = cpu.percent != null ? cpu.percent + '%' : '—';
            setBar(document.querySelector('[data-jp-nas-cpu-bar]'), cpu.percent);

            const diskDisplay = document.querySelector('[data-jp-nas-disk-display]');
            if (diskDisplay) diskDisplay.textContent = disk.display || '—';
            setBar(document.querySelector('[data-jp-nas-disk-bar]'), disk.used_percent);
            const diskPct = document.querySelector('[data-jp-nas-disk-pct]');
            if (diskPct) diskPct.textContent = (disk.used_percent != null ? disk.used_percent : '—') + (disk.used_percent != null ? '%' : '');

            renderShares(metrics.shares || [], 'jp-nas-shares');
            renderVolumes(metrics.volumes || []);

            const backupRemote = document.querySelector('[data-jp-nas-backup-remote]');
            if (backupRemote) backupRemote.textContent = backup.remote || '—';
            const backupSize = document.querySelector('[data-jp-nas-backup-size]');
            if (backupSize) backupSize.textContent = backup.display || '—';
            const backupPct = document.querySelector('[data-jp-nas-backup-pct]');
            if (backupPct) backupPct.textContent = backup.used_percent != null ? ' (' + backup.used_percent + '%)' : '';

            if (performanceTabActive) {
                applyPerformanceMetrics(metrics);
            }
        }

        if (updatedEl) {
            updatedEl.textContent = 'Cập nhật ' + new Date().toLocaleTimeString('vi-VN');
        }
    }

    function applyMetrics(metrics) {
        const ram = metrics.ram || {};
        const cpu = metrics.cpu || {};
        const disk = metrics.disk || {};
        const backup = metrics.backup || {};

        const ramDisplay = document.querySelector('[data-jp-nas-ram-display]');
        if (ramDisplay) ramDisplay.textContent = ram.display || '—';
        setBar(document.querySelector('[data-jp-nas-ram-bar]'), ram.used_percent);
        const ramPct = document.querySelector('[data-jp-nas-ram-pct]');
        if (ramPct) ramPct.textContent = (ram.used_percent != null ? ram.used_percent : '—') + (ram.used_percent != null ? '%' : '');

        const cpuDisplay = document.querySelector('[data-jp-nas-cpu-display]');
        if (cpuDisplay) cpuDisplay.textContent = cpu.percent != null ? cpu.percent + '%' : '—';
        setBar(document.querySelector('[data-jp-nas-cpu-bar]'), cpu.percent);

        const diskDisplay = document.querySelector('[data-jp-nas-disk-display]');
        if (diskDisplay) diskDisplay.textContent = disk.display || '—';
        setBar(document.querySelector('[data-jp-nas-disk-bar]'), disk.used_percent);
        const diskPct = document.querySelector('[data-jp-nas-disk-pct]');
        if (diskPct) diskPct.textContent = (disk.used_percent != null ? disk.used_percent : '—') + (disk.used_percent != null ? '%' : '');

        renderShares(metrics.shares || [], 'jp-nas-shares');
        renderVolumes(metrics.volumes || []);

        const backupRemote = document.querySelector('[data-jp-nas-backup-remote]');
        if (backupRemote) backupRemote.textContent = backup.remote || '—';
        const backupSize = document.querySelector('[data-jp-nas-backup-size]');
        if (backupSize) backupSize.textContent = backup.display || '—';
        const backupPct = document.querySelector('[data-jp-nas-backup-pct]');
        if (backupPct) backupPct.textContent = backup.used_percent != null ? ' (' + backup.used_percent + '%)' : '';

        applyPerformanceMetrics(metrics);
        renderWidgets(metrics.widgets || {}, metrics);

        if (updatedEl) {
            updatedEl.textContent = 'Cập nhật ' + new Date().toLocaleTimeString('vi-VN');
        }
    }

    async function refreshMetrics(options) {
        if (!metricsUrl) return;
        const initial = options && options.initial === true;
        const manual = options && options.manual === true;
        const scope = (options && options.scope) || activeScope;
        if (initial) loading.showInitial();
        else if (manual) loading.showButtonBusy();
        try {
            const url = metricsUrl + (metricsUrl.indexOf('?') >= 0 ? '&' : '?') + 'scope=' + encodeURIComponent(scope);
            const resp = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            const data = await resp.json();
            if (data.status === 'success' && data.metrics) {
                applyMetricsForScope(data.metrics, scope);
            } else if (updatedEl) {
                updatedEl.textContent = 'Lỗi tải metrics' + (data.message ? ': ' + data.message : '');
            }
        } catch (err) {
            console.warn('NAS metrics refresh failed', err);
            if (updatedEl) updatedEl.textContent = 'Lỗi kết nối metrics';
        } finally {
            if (initial) loading.hideInitial();
            else if (manual) loading.hideButtonBusy();
        }
    }

    function bindTabScope(btn, scope) {
        if (!btn) return;
        btn.addEventListener('shown.bs.tab', function () {
            setActiveScope(scope);
            if (scope === 'performance') {
                performanceTabActive = true;
                initPerformanceCharts();
            } else {
                performanceTabActive = false;
            }
            scheduleRefresh();
            refreshMetrics({ manual: false, scope: scope });
        });
        if (scope === 'performance') {
            btn.addEventListener('hidden.bs.tab', function () {
                performanceTabActive = false;
                scheduleRefresh();
            });
        }
    }

    function scheduleRefresh() {
        if (refreshTimer) clearInterval(refreshTimer);
        const sec = performanceTabActive ? performanceRefreshSec : refreshSec;
        if (sec > 0) {
            refreshTimer = setInterval(function () {
                refreshMetrics({ manual: false, scope: activeScope });
            }, sec * 1000);
        }
    }

    bindTabScope(overviewTabBtn, 'overview');
    bindTabScope(performanceTabBtn, 'performance');
    bindTabScope(dsmTabBtn, 'full');

    if (performanceTab && performanceTab.classList.contains('active')) {
        performanceTabActive = true;
        setActiveScope('performance');
    }

    if (refreshBtn) {
        refreshBtn.addEventListener('click', function () {
            refreshMetrics({ manual: true, scope: activeScope });
        });
    }

    if (updatedEl) {
        updatedEl.textContent = 'Cập nhật ' + new Date().toLocaleTimeString('vi-VN');
    }

    scheduleRefresh();
    refreshMetrics({ initial: true, scope: activeScope });
})();
