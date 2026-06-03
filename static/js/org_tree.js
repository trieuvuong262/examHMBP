/**
 * Sơ đồ cây ngang — Công ty → Phòng ban → Bộ phận → Vị trí (D3).
 * Kéo / zoom; header cột HTML; bấm ô để sửa.
 */
(function () {
    'use strict';

    const PILL_RX = 8;
    const NODE_H = 56;
    const NODE_W = 232;
    const HEADER_H = 44;
    const COLUMN_LABELS = ['Tổng / Giám đốc', 'Phòng ban', 'Bộ phận', 'Vị trí'];

    function showError(mount, msg) {
        mount.innerHTML = `<div class="alert alert-warning m-3">${msg}</div>`;
    }

    function pillSize(level, hasSubtitle) {
        if (level === 'root') {
            return { w: 236, h: hasSubtitle ? 52 : 42 };
        }
        if (level === 'department') {
            return { w: 218, h: 44 };
        }
        if (level === 'position') {
            return { w: 196, h: 36 };
        }
        return { w: 208, h: 40 };
    }

    function elbowPath(d) {
        const sw = pillSize(d.source.data.level || 'item', !!d.source.data.subtitle).w;
        const sx = d.source.y + sw;
        const sy = d.source.x;
        const tx = d.target.y;
        const ty = d.target.x;
        const mx = (sx + tx) / 2;
        return `M${sx},${sy}H${mx}V${ty}H${tx}`;
    }

    function truncate(text, max) {
        const s = String(text || '');
        return s.length > max ? `${s.slice(0, max - 1)}…` : s;
    }

    function fillUrl(tpl, vals) {
        let u = tpl || '';
        Object.entries(vals).forEach(([key, val]) => {
            u = u.split(`{${key}}`).join(encodeURIComponent(String(val ?? '')));
        });
        return u;
    }

    function primaryHref(nodeData, urls) {
        const level = nodeData.level;
        const id = nodeData.id;
        if (level === 'department' && id && urls.deptEdit) {
            return urls.deptEdit.replace('{id}', String(id));
        }
        if (level === 'division' && id && urls.divEdit) {
            return urls.divEdit.replace('{id}', String(id));
        }
        if (level === 'position' && id && urls.positionEdit) {
            return urls.positionEdit.replace('{id}', String(id));
        }
        if (level === 'position' && urls.userAdd) {
            return fillUrl(urls.userAdd, {
                dept_id: nodeData.dept_id || '',
                div_id: nodeData.division_id || '',
                position: nodeData.name || '',
            });
        }
        if (level === 'root' && urls.userList) {
            return urls.userList;
        }
        return null;
    }

    function buildActions(nodeData, urls) {
        const level = nodeData.level;
        const id = nodeData.id;
        const deptId = nodeData.dept_id;
        const divId = nodeData.division_id;
        const out = [];

        if (level === 'department' && id) {
            if (urls.divisionAdd) {
                out.push({ href: urls.divisionAdd.replace('{dept_id}', String(id)), title: 'Thêm bộ phận', glyph: '+' });
            }
            if (urls.deptPermissions) {
                out.push({ href: urls.deptPermissions.replace('{id}', String(id)), title: 'Phân quyền', glyph: '◆' });
            }
            if (urls.deptEdit) {
                out.push({ href: urls.deptEdit.replace('{id}', String(id)), title: 'Sửa phòng ban', glyph: '✎' });
            }
            if (urls.deptDelete) {
                out.push({ href: urls.deptDelete.replace('{id}', String(id)), title: 'Xóa', glyph: '×', danger: true });
            }
        }

        if (level === 'division' && id) {
            if (urls.positionAdd) {
                out.push({
                    href: fillUrl(urls.positionAdd, { dept_id: deptId || '', div_id: id }),
                    title: 'Thêm vị trí',
                    glyph: '+',
                });
            }
            if (urls.divEdit) {
                out.push({ href: urls.divEdit.replace('{id}', String(id)), title: 'Sửa bộ phận', glyph: '✎' });
            }
            if (urls.divDelete) {
                out.push({ href: urls.divDelete.replace('{id}', String(id)), title: 'Xóa', glyph: '×', danger: true });
            }
        }

        if (level === 'position') {
            if (id && urls.positionEdit) {
                out.push({ href: urls.positionEdit.replace('{id}', String(id)), title: 'Sửa vị trí', glyph: '✎' });
            }
            if (id && urls.positionDelete) {
                out.push({ href: urls.positionDelete.replace('{id}', String(id)), title: 'Xóa vị trí', glyph: '×', danger: true });
            }
            if (urls.userAdd && divId) {
                out.push({
                    href: fillUrl(urls.userAdd, {
                        dept_id: deptId || '',
                        div_id: divId,
                        position: nodeData.name || '',
                    }),
                    title: 'Thêm nhân viên',
                    glyph: '+',
                });
            }
        }

        if (level === 'root' && urls.userList) {
            out.push({ href: urls.userList, title: 'Nhân sự', glyph: 'NS' });
        }

        return out;
    }

    function columnPositions(nodes) {
        const colX = new Map();
        nodes.forEach((n) => {
            const cur = colX.get(n.depth);
            if (cur === undefined || n.y < cur) {
                colX.set(n.depth, n.y);
            }
        });
        return COLUMN_LABELS.map((label, depth) => ({
            label,
            depth,
            x: colX.has(depth) ? colX.get(depth) : depth * NODE_W,
            w: NODE_W - 4,
        }));
    }

    function renderHtmlHeaders(trackEl, columns, marginLeft) {
        if (!trackEl) return;
        trackEl.innerHTML = '';
        columns.forEach((col) => {
            const el = document.createElement('div');
            el.className = 'jp-org-chart-col-label';
            el.style.left = `${marginLeft + col.x}px`;
            el.style.width = `${col.w}px`;
            el.textContent = col.label;
            el.setAttribute('data-depth', String(col.depth));
            trackEl.appendChild(el);
        });
    }

    function applySyncedTransform(trackEl, zoomRoot, transform) {
        if (trackEl) {
            trackEl.style.transform = `translate(${transform.x}px, 0px) scale(${transform.k}, 1)`;
            trackEl.style.transformOrigin = '0 0';
        }
        zoomRoot.attr('transform', transform);
    }

    window.jpOrgTreeInit = function jpOrgTreeInit() {
        const mount = document.getElementById('jp-org-tree-mount');
        const headerTrack = document.getElementById('jp-org-headers-track');
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
        const margin = { top: 16, right: 40, bottom: 20, left: 16 };

        const root = d3.hierarchy(data);
        d3.tree()
            .nodeSize([NODE_H, NODE_W])
            .separation((a, b) => (a.parent === b.parent ? 1 : 1.06))(root);

        const nodes = root.descendants();
        const links = root.links();
        const columns = columnPositions(nodes);
        renderHtmlHeaders(headerTrack, columns, margin.left);

        const yMin = d3.min(nodes, (d) => d.x) ?? 0;
        const yMax = d3.max(nodes, (d) => d.x) ?? 0;
        const xMax = d3.max(nodes, (d) => d.y) ?? 0;
        const maxPillH = d3.max(nodes, (d) => pillSize(d.data.level || 'item', !!d.data.subtitle).h) ?? NODE_H;
        const innerH = yMax - yMin + maxPillH;
        const chartW = xMax + 56;
        const chartH = innerH;
        const svgW = chartW + margin.left + margin.right;
        const svgH = chartH + margin.top + margin.bottom;

        const svg = d3.select(mount)
            .append('svg')
            .attr('class', 'jp-org-tree-svg')
            .attr('width', svgW)
            .attr('height', svgH);

        const defs = svg.append('defs');
        defs.append('marker')
            .attr('id', 'jp-org-arrow')
            .attr('viewBox', '0 -4 8 8')
            .attr('refX', 6)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-4L8,0L0,4')
            .attr('fill', '#94a3b8');

        const zoomRoot = svg.append('g').attr('class', 'jp-org-tree-zoom');

        zoomRoot.append('rect')
            .attr('class', 'jp-org-tree-pan-surface')
            .attr('x', 0)
            .attr('y', 0)
            .attr('width', svgW)
            .attr('height', svgH)
            .attr('fill', 'transparent');

        const g = zoomRoot.append('g')
            .attr('class', 'jp-org-tree-chart')
            .attr('transform', `translate(${margin.left},${margin.top - yMin})`);

        g.append('g')
            .attr('class', 'jp-org-tree-col-guides')
            .selectAll('line')
            .data(columns)
            .join('line')
            .attr('class', 'jp-org-tree-col-guide')
            .attr('x1', (d) => d.x + d.w / 2)
            .attr('x2', (d) => d.x + d.w / 2)
            .attr('y1', -8)
            .attr('y2', innerH + 8);

        g.append('g')
            .attr('class', 'jp-org-tree-links')
            .selectAll('path')
            .data(links)
            .join('path')
            .attr('class', 'jp-org-tree-link')
            .attr('fill', 'none')
            .attr('d', elbowPath);

        const nodeG = g.append('g')
            .attr('class', 'jp-org-tree-nodes')
            .selectAll('g')
            .data(nodes)
            .join('g')
            .attr('class', (d) => {
                const clickable = primaryHref(d.data, urls) ? ' is-clickable' : '';
                return `jp-org-tree-node jp-org-tree-node--${d.data.level || 'item'}${clickable}`;
            })
            .attr('transform', (d) => `translate(${d.y},${d.x})`);

        nodeG.each(function (d) {
            const sel = d3.select(this);
            const level = d.data.level || 'item';
            const hasSub = !!d.data.subtitle;
            const { w: pillW, h: pillH } = pillSize(level, hasSub);
            const href = primaryHref(d.data, urls);
            const actions = buildActions(d.data, urls);

            const pill = sel.append('g')
                .attr('class', 'jp-org-tree-pill')
                .style('cursor', href ? 'pointer' : 'default');

            pill.append('rect')
                .attr('class', 'jp-org-tree-pill-rect')
                .attr('x', 0)
                .attr('y', -pillH / 2)
                .attr('width', pillW)
                .attr('height', pillH)
                .attr('rx', PILL_RX)
                .attr('ry', PILL_RX);

            if (href) {
                pill.on('click', (ev) => {
                    if (ev.defaultPrevented) return;
                    window.location.href = href;
                });
            }

            pill.append('text')
                .attr('class', 'jp-org-tree-pill-label')
                .attr('x', 14)
                .attr('y', hasSub ? -2 : 5)
                .text(truncate(d.data.name, 28));

            if (d.data.subtitle) {
                pill.append('text')
                    .attr('class', 'jp-org-tree-pill-sub')
                    .attr('x', 14)
                    .attr('y', 14)
                    .text(truncate(d.data.subtitle, 30));
            }

            const badgeW = 30;
            const badgeH = 22;
            const badgeX = pillW - badgeW - 8;
            pill.append('rect')
                .attr('class', 'jp-org-tree-pill-badge-bg')
                .attr('x', badgeX)
                .attr('y', -badgeH / 2)
                .attr('width', badgeW)
                .attr('height', badgeH)
                .attr('rx', 5)
                .attr('ry', 5);

            pill.append('text')
                .attr('class', 'jp-org-tree-pill-badge-txt')
                .attr('x', badgeX + badgeW / 2)
                .attr('y', 5)
                .attr('text-anchor', 'middle')
                .text(String(d.data.count ?? 0));

            if (actions.length) {
                const menu = sel.append('g')
                    .attr('class', 'jp-org-tree-actions')
                    .attr('transform', `translate(${pillW - 4},${-pillH / 2 - 4})`);

                actions.forEach((act, i) => {
                    const ag = menu.append('g')
                        .attr('class', 'jp-org-tree-action')
                        .attr('transform', `translate(${i * 22},0)`);

                    const link = ag.append('a')
                        .attr('href', act.href)
                        .attr('class', `jp-org-tree-action-link${act.danger ? ' is-danger' : ''}`)
                        .attr('title', act.title)
                        .attr('aria-label', act.title)
                        .on('click', (ev) => ev.stopPropagation());

                    link.append('rect')
                        .attr('class', 'jp-org-tree-action-bg')
                        .attr('width', 20)
                        .attr('height', 20)
                        .attr('rx', 4);
                    link.append('text')
                        .attr('class', 'jp-org-tree-action-icon')
                        .attr('x', 10)
                        .attr('y', 14)
                        .attr('text-anchor', 'middle')
                        .text(act.glyph);
                });
            }

            pill.append('title').text(`${d.data.name} — ${d.data.count ?? 0} NV`);
        });

        const zoom = d3.zoom()
            .scaleExtent([0.35, 2.5])
            .filter((event) => {
                if (event.type === 'wheel') return true;
                if (event.type === 'dblclick') return false;
                const target = event.target;
                if (target && target.closest) {
                    if (target.closest('.jp-org-tree-action-link')) return false;
                }
                return true;
            })
            .on('zoom', (event) => {
                applySyncedTransform(headerTrack, zoomRoot, event.transform);
            });

        svg.call(zoom).on('dblclick.zoom', null);

        const vp = document.getElementById('jp-org-chart-viewport');
        const vpW = (vp && vp.clientWidth) || mount.clientWidth || 900;
        const fitScale = Math.min(1.05, Math.max(0.55, (vpW - 24) / svgW));
        const initial = d3.zoomIdentity
            .translate(12, 8)
            .scale(fitScale);
        svg.call(zoom.transform, initial);

        mount.classList.add('jp-org-tree-mount--ready');
    };

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
