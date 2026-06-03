/**
 * Sơ đồ cây ngang — Công ty → Phòng ban → Bộ phận → Vị trí (D3).
 */
(function () {
    'use strict';

    function showError(mount, msg) {
        mount.innerHTML = `<div class="alert alert-warning m-3">${msg}</div>`;
    }

    window.jpOrgTreeInit = function jpOrgTreeInit() {
        const mount = document.getElementById('jp-org-tree-mount');
        if (!mount) return;

        if (typeof d3 === 'undefined') {
            showError(mount, 'Không tải được thư viện D3. Tải lại trang hoặc liên hệ IT.');
            return;
        }
        if (!window.JP_ORG_TREE) {
            showError(mount, 'Không có dữ liệu sơ đồ. Tải lại trang.');
            return;
        }

        mount.innerHTML = '';
        const data = window.JP_ORG_TREE;
        const urls = window.JP_ORG_URLS || {};

        const nodeH = 52;
        const nodeW = 260;
        const margin = { top: 28, right: 48, bottom: 28, left: 20 };

        const root = d3.hierarchy(data);
        const layout = d3.tree()
            .nodeSize([nodeH, nodeW])
            .separation((a, b) => (a.parent === b.parent ? 1 : 1.2));
        layout(root);

        const nodes = root.descendants();
        const links = root.links();
        const yMin = d3.min(nodes, (d) => d.x) ?? 0;
        const yMax = d3.max(nodes, (d) => d.x) ?? 0;
        const xMax = d3.max(nodes, (d) => d.y) ?? 0;
        const innerH = yMax - yMin + nodeH;
        const svgW = xMax + margin.left + margin.right + 80;
        const svgH = innerH + margin.top + margin.bottom;

        const svg = d3.select(mount)
            .append('svg')
            .attr('class', 'jp-org-tree-svg')
            .attr('width', svgW)
            .attr('height', svgH)
            .attr('viewBox', `0 0 ${svgW} ${svgH}`);

        const g = svg.append('g')
            .attr('transform', `translate(${margin.left},${margin.top - yMin})`);

        const linkGen = d3.linkHorizontal()
            .x((d) => d.y)
            .y((d) => d.x);

        g.append('g')
            .attr('class', 'jp-org-tree-links')
            .selectAll('path')
            .data(links)
            .join('path')
            .attr('class', 'jp-org-tree-link')
            .attr('d', linkGen);

        const nodeG = g.append('g')
            .attr('class', 'jp-org-tree-nodes')
            .selectAll('g')
            .data(nodes)
            .join('g')
            .attr('class', (d) => `jp-org-tree-node jp-org-tree-node--${d.data.level || 'item'}`)
            .attr('transform', (d) => `translate(${d.y},${d.x})`);

        nodeG.each(function (d) {
            const sel = d3.select(this);
            const level = d.data.level || 'item';
            const pillW = level === 'root' ? 200 : level === 'department' ? 190 : 175;
            const pillH = d.data.subtitle ? 46 : 36;
            const rx = pillH / 2;

            sel.append('rect')
                .attr('class', 'jp-org-tree-pill-rect')
                .attr('x', 0)
                .attr('y', -pillH / 2)
                .attr('width', pillW)
                .attr('height', pillH)
                .attr('rx', rx)
                .attr('ry', rx);

            sel.append('text')
                .attr('class', 'jp-org-tree-pill-label')
                .attr('x', 12)
                .attr('y', d.data.subtitle ? -4 : 4)
                .text(truncate(d.data.name, 28));

            if (d.data.subtitle) {
                sel.append('text')
                    .attr('class', 'jp-org-tree-pill-sub')
                    .attr('x', 12)
                    .attr('y', 12)
                    .text(truncate(d.data.subtitle, 32));
            }

            const badgeX = pillW - 8;
            sel.append('circle')
                .attr('class', 'jp-org-tree-pill-badge-bg')
                .attr('cx', badgeX)
                .attr('cy', 0)
                .attr('r', 14);

            sel.append('text')
                .attr('class', 'jp-org-tree-pill-badge-txt')
                .attr('x', badgeX)
                .attr('y', 4)
                .attr('text-anchor', 'middle')
                .text(String(d.data.count ?? 0));

            const title = `${d.data.name} — ${d.data.count ?? 0} NV`;
            sel.append('title').text(title);
        });

        mount.style.minHeight = `${Math.min(svgH, 640)}px`;
    };

    function truncate(text, max) {
        const s = String(text || '');
        return s.length > max ? `${s.slice(0, max - 1)}…` : s;
    }

    function boot() {
        if (document.getElementById('jp-org-tree-data') && !window.JP_ORG_TREE) {
            try {
                window.JP_ORG_TREE = JSON.parse(document.getElementById('jp-org-tree-data').textContent);
                const u = document.getElementById('jp-org-urls-data');
                if (u) window.JP_ORG_URLS = JSON.parse(u.textContent);
            } catch (e) {
                console.error(e);
            }
        }
        window.jpOrgTreeInit();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
