(function () {
    'use strict';

    const root = document.getElementById('jp-vps-monitor');
    if (!root) return;

    const metricsUrl = root.dataset.metricsUrl;
    const refreshSec = parseInt(root.dataset.autoRefresh || '30', 10);
    const performanceRefreshSec = parseInt(root.dataset.performanceRefresh || '5', 10);
    const refreshBtn = document.getElementById('jp-vps-refresh');
    const updatedEl = document.getElementById('jp-vps-updated');
    const loadingEl = document.getElementById('jp-vps-loading');
    const performanceTab = document.getElementById('jp-vps-tab-performance');
    const performanceTabBtn = document.getElementById('jp-vps-tab-performance-btn');
    const openContainerIds = new Set();

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
                x: {
                    ticks: { maxTicksLimit: 6, maxRotation: 0 },
                },
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
            cpu: new Chart(document.getElementById('jp-vps-chart-cpu'), {
                type: 'line',
                data: {
                    labels: chartHistory.labels,
                    datasets: [lineDataset('CPU', '#16a34a', 'rgba(22, 163, 74, 0.12)')],
                },
                options: chartOptions(),
            }),
            ram: new Chart(document.getElementById('jp-vps-chart-ram'), {
                type: 'line',
                data: {
                    labels: chartHistory.labels,
                    datasets: [lineDataset('RAM', '#2563eb', 'rgba(37, 99, 235, 0.12)')],
                },
                options: chartOptions(),
            }),
            disk: new Chart(document.getElementById('jp-vps-chart-disk'), {
                type: 'line',
                data: {
                    labels: chartHistory.labels,
                    datasets: [lineDataset('SSD', '#d97706', 'rgba(217, 119, 6, 0.12)')],
                },
                options: chartOptions(),
            }),
        };
    }

    function updatePerformanceCharts() {
        if (!performanceCharts) return;
        performanceCharts.cpu.data.labels = chartHistory.labels;
        performanceCharts.cpu.data.datasets[0].data = chartHistory.cpu.slice();
        performanceCharts.cpu.update('none');

        performanceCharts.ram.data.labels = chartHistory.labels;
        performanceCharts.ram.data.datasets[0].data = chartHistory.ram.slice();
        performanceCharts.ram.update('none');

        performanceCharts.disk.data.labels = chartHistory.labels;
        performanceCharts.disk.data.datasets[0].data = chartHistory.disk.slice();
        performanceCharts.disk.update('none');
    }

    function bindContainerToggles(scope) {
        (scope || document).querySelectorAll('.jp-vps-container-toggle').forEach(function (btn) {
            const target = btn.getAttribute('data-bs-target');
            if (!target) return;
            const panel = document.querySelector(target);
            if (!panel) return;
            panel.addEventListener('show.bs.collapse', function () {
                btn.querySelector('.jp-vps-chevron')?.classList.replace('bi-chevron-right', 'bi-chevron-down');
                openContainerIds.add(target.replace('#', ''));
            });
            panel.addEventListener('hide.bs.collapse', function () {
                btn.querySelector('.jp-vps-chevron')?.classList.replace('bi-chevron-down', 'bi-chevron-right');
                openContainerIds.delete(target.replace('#', ''));
            });
        });
    }

    function renderContainerDetail(row) {
        const id = escapeHtml(row.id);
        const expanded = openContainerIds.has('jp-vps-container-' + row.id);
        const chevron = expanded ? 'bi-chevron-down' : 'bi-chevron-right';
        const showClass = expanded ? ' show' : '';
        const cpu = row.cpu_percent != null ? row.cpu_percent + '%' : '—';
        const memPct = row.memory_percent != null ? row.memory_percent + '%' : '—';
        return (
            '<tr class="jp-vps-container-row">' +
            '<td class="small">' +
            '<button type="button" class="btn btn-link btn-sm p-0 text-start font-monospace text-decoration-none jp-vps-container-toggle" ' +
            'data-bs-toggle="collapse" data-bs-target="#jp-vps-container-' + id + '" aria-expanded="' + (expanded ? 'true' : 'false') + '">' +
            '<i class="bi ' + chevron + ' me-1 jp-vps-chevron"></i>' + escapeHtml(row.name) +
            '</button></td>' +
            '<td>' + escapeHtml(row.memory_display) + '</td>' +
            '<td>' + cpu + '</td>' +
            '<td class="text-end">' + memPct + '</td>' +
            '</tr>' +
            '<tr class="collapse bg-light' + showClass + '" id="jp-vps-container-' + id + '">' +
            '<td colspan="4" class="small p-3">' +
            '<div class="row g-2">' +
            '<div class="col-md-6">' +
            '<div><span class="text-muted">ID:</span> <code>' + id + '</code></div>' +
            '<div><span class="text-muted">Image:</span> <code>' + escapeHtml(row.image) + '</code></div>' +
            '<div><span class="text-muted">Trạng thái:</span> ' + escapeHtml(row.state) + ' — ' + escapeHtml(row.status) + '</div>' +
            '</div><div class="col-md-6">' +
            '<div><span class="text-muted">Cache RAM:</span> ' + formatBytes(row.memory_cache_bytes) + '</div>' +
            '<div><span class="text-muted">Mạng ↓/↑:</span> ' + formatBytes(row.network_rx_bytes) + ' / ' + formatBytes(row.network_tx_bytes) + '</div>' +
            '<div><span class="text-muted">Tiến trình:</span> ' + escapeHtml(row.pids) + '</div>' +
            '</div></div></td></tr>'
        );
    }

    function renderContainers(rows) {
        const tbody = document.getElementById('jp-vps-containers');
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="4" class="text-muted small p-3">Chưa có dữ liệu container.</td></tr>';
            return;
        }
        tbody.innerHTML = rows.map(renderContainerDetail).join('');
        bindContainerToggles(tbody);
    }

    function renderProcesses(rows) {
        const tbody = document.getElementById('jp-vps-processes');
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-muted small p-3">Chưa có dữ liệu tiến trình.</td></tr>';
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

    function renderPerfContainers(rows) {
        const tbody = document.getElementById('jp-vps-perf-containers');
        if (!tbody) return;
        if (!rows || !rows.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-muted small p-3">Chưa có dữ liệu container.</td></tr>';
            return;
        }
        const sorted = rows.slice().sort(function (a, b) {
            return (Number(b.memory_percent) || 0) - (Number(a.memory_percent) || 0);
        });
        tbody.innerHTML = sorted.map(function (row) {
            const cpu = row.cpu_percent != null ? row.cpu_percent + '%' : '—';
            const memPct = row.memory_percent != null ? row.memory_percent + '%' : '—';
            return (
                '<tr>' +
                '<td class="font-monospace small">' + escapeHtml(row.name) + '</td>' +
                '<td class="small text-muted">' + escapeHtml(row.image) + '</td>' +
                '<td class="small">' + escapeHtml(row.state) + '</td>' +
                '<td class="text-end">' + escapeHtml(row.memory_display) + '</td>' +
                '<td class="text-end">' + cpu + '</td>' +
                '<td class="text-end">' + memPct + '</td>' +
                '<td class="text-end">' + escapeHtml(row.pids) + '</td>' +
                '</tr>'
            );
        }).join('');
    }

    function applyResourceCards(metrics) {
        const ram = metrics.ram || {};
        const cpu = metrics.cpu || {};
        const disk = metrics.disk || {};

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
    }

    function applyPerformanceMetrics(metrics) {
        const ram = metrics.ram || {};
        const cpu = metrics.cpu || {};
        const disk = metrics.disk || {};

        const perfCpu = document.querySelector('[data-jp-vps-perf-cpu]');
        if (perfCpu) perfCpu.textContent = cpu.percent != null ? cpu.percent + '%' : '—';
        const perfLoad = document.querySelector('[data-jp-vps-perf-load]');
        if (perfLoad && cpu.loadavg) perfLoad.textContent = cpu.loadavg['1m'];

        const perfRam = document.querySelector('[data-jp-vps-perf-ram]');
        if (perfRam) perfRam.textContent = ram.used_percent != null ? ram.used_percent + '%' : '—';
        const perfRamDetail = document.querySelector('[data-jp-vps-perf-ram-detail]');
        if (perfRamDetail) {
            perfRamDetail.textContent = ram.display || (formatBytes(ram.used_bytes) + ' / ' + formatBytes(ram.total_bytes));
        }

        const perfDisk = document.querySelector('[data-jp-vps-perf-disk]');
        if (perfDisk) perfDisk.textContent = disk.used_percent != null ? disk.used_percent + '%' : '—';
        const perfDiskDetail = document.querySelector('[data-jp-vps-perf-disk-detail]');
        if (perfDiskDetail && disk.used_bytes != null) {
            perfDiskDetail.textContent = formatBytes(disk.used_bytes) + ' / ' + formatBytes(disk.total_bytes);
        }

        renderProcesses(metrics.processes || []);
        const containers = (metrics.docker && metrics.docker.containers) || [];
        if (containers.length) {
            renderPerfContainers(containers);
        }

        if (performanceTabActive) {
            pushChartHistory(metrics);
            if (!performanceCharts) initPerformanceCharts();
            updatePerformanceCharts();
        }
    }

    const overviewTabBtn = document.getElementById('jp-vps-tab-overview-btn');

    let activeScope = 'full';

    function setActiveScope(scope) {
        activeScope = scope || 'full';
    }

    function applyMetricsForScope(metrics, scope) {
        if (scope === 'performance') {
            applyPerformanceMetrics(metrics);
            if (!performanceTabActive) {
                applyResourceCards(metrics);
            }
        } else {
            applyMetrics(metrics);
        }
        if (updatedEl) {
            updatedEl.textContent = 'Cập nhật ' + new Date().toLocaleTimeString('vi-VN');
        }
    }

    function applyMetrics(metrics) {
        const summary = (metrics.docker && metrics.docker.summary) || {};

        applyResourceCards(metrics);

        renderContainers((metrics.docker && metrics.docker.containers) || []);

        const imagesEl = document.querySelector('[data-jp-vps-images]');
        if (imagesEl) imagesEl.textContent = formatBytes(summary.images_bytes);
        const imagesReclaim = document.querySelector('[data-jp-vps-images-reclaim]');
        if (imagesReclaim) imagesReclaim.textContent = formatBytes(summary.images_reclaimable_bytes);
        const volumesEl = document.querySelector('[data-jp-vps-volumes]');
        if (volumesEl) volumesEl.textContent = formatBytes(summary.volumes_bytes);
        const containerdEl = document.querySelector('[data-jp-vps-containerd]');
        if (containerdEl) containerdEl.textContent = formatBytes(summary.containerd_bytes);

        applyPerformanceMetrics(metrics);

        if (updatedEl) {
            const now = new Date();
            updatedEl.textContent = 'Cập nhật ' + now.toLocaleTimeString('vi-VN');
        }
    }

    async function refreshMetrics(options) {
        if (!metricsUrl) return false;
        const initial = options && options.initial === true;
        const manual = options && options.manual === true;
        const quiet = options && options.quiet === true;
        const scope = (options && options.scope) || activeScope;
        if (initial) loading.showInitial();
        else if (manual) loading.showButtonBusy();
        let ok = false;
        try {
            const url = metricsUrl + (metricsUrl.indexOf('?') >= 0 ? '&' : '?') + 'scope=' + encodeURIComponent(scope);
            const resp = await fetch(url, {
                headers: { 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin',
            });
            const data = await resp.json();
            if (data.status === 'success' && data.metrics) {
                applyMetricsForScope(data.metrics, scope);
                ok = true;
            }
        } catch (err) {
            console.warn('VPS metrics refresh failed', err);
        } finally {
            if (initial) loading.hideInitial();
            else if (manual) loading.hideButtonBusy();
        }
        return ok;
    }

    async function loadInitialMetrics() {
        if (activeScope === 'performance') {
            await refreshMetrics({ initial: true, scope: 'performance' });
            return;
        }
        loading.showInitial();
        try {
            await refreshMetrics({ scope: 'performance', quiet: true });
        } finally {
            loading.hideInitial();
        }
        await refreshMetrics({ scope: activeScope, quiet: true });
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

    bindTabScope(overviewTabBtn, 'full');
    bindTabScope(performanceTabBtn, 'performance');

    bindContainerToggles(root);

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
        const now = new Date();
        updatedEl.textContent = '—';
    }

    scheduleRefresh();
    loadInitialMetrics();
})();
