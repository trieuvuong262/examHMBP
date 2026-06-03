/**
 * Sơ đồ cây ngang — Công ty → PB → BP → Vị trí → Nhân viên (ẩn/mở).
 */
(function () {
    'use strict';

    /** Khoảng cách ngang giữa các cột — ×1.5 để đường nối có chỗ bo góc đẹp hơn. */
    const WIDTH_SCALE = 1.5;

    const LAYOUT = {
        widthScale: WIDTH_SCALE,
        nodeWMin: Math.round(300 * WIDTH_SCALE),
        nodeWMax: Math.round(520 * WIDTH_SCALE),
        fillViewport: true,
        nodeH: 50,
        nodeHEmployee: 36,
        pillScale: 1.05,
        chartPadRight: Math.round(100 * WIDTH_SCALE),
    };

    const PILL_RX = 10;
    const COLUMN_LABELS = [
        'Tổng / Giám đốc',
        'Phòng ban',
        'Bộ phận',
        'Vị trí',
        'Nhân viên',
    ];

    const ZOOM = {
        min: 0.5,
        max: 2,
        wheelFactor: 0.00065,
    };

    const ACTION = { size: 22, gap: 2 };

    const chartState = {
        collapsed: new Set(),
        fullData: null,
        urls: {},
        savedTransform: null,
        headerSync: null,
        zoomRaf: null,
    };

    function resolveNodeW(viewportWidth, maxDepth) {
        const levels = Math.max(maxDepth + 1, COLUMN_LABELS.length);
        if (!LAYOUT.fillViewport) {
            return LAYOUT.nodeWMin;
        }
        const usable = Math.max(800, viewportWidth - 40);
        const perLevel = usable / levels;
        return Math.min(LAYOUT.nodeWMax, Math.max(LAYOUT.nodeWMin, perLevel));
    }

    function showError(mount, msg) {
        mount.innerHTML = `<div class="alert alert-warning m-3">${msg}</div>`;
    }

    function pillSize(level, hasSubtitle, nodeW) {
        const gap = Math.max(24, nodeW - 200);
        const s = LAYOUT.pillScale;
        if (level === 'employee') {
            return { w: Math.round(Math.max(160, nodeW - 28) * s), h: 32 };
        }
        if (level === 'root') {
            return { w: Math.round((200 + gap * 0.5) * s), h: hasSubtitle ? 52 : 42 };
        }
        if (level === 'department') {
            return { w: Math.round((188 + gap * 0.45) * s), h: 44 };
        }
        if (level === 'position') {
            return { w: Math.round(Math.max(nodeW - 12, 220 + gap * 0.7) * s), h: 40 };
        }
        return { w: Math.round((178 + gap * 0.5) * s), h: 40 };
    }

    function actionStripWidth(actions) {
        if (!actions || !actions.length) return 0;
        return actions.length * (ACTION.size + ACTION.gap) + 6;
    }

    function nodeContentRight(nodes, nodeW, urls) {
        return d3.max(nodes, (d) => {
            const level = d.data.level || 'item';
            const { w: pillW } = pillSize(level, !!d.data.subtitle, nodeW);
            const actions = buildActions(d.data, urls);
            const chevron = level === 'position' ? 18 : 0;
            return d.y + pillW + actionStripWidth(actions) + chevron;
        }) ?? 0;
    }

    function ellipsizeSvgText(textSel, fullText, maxWidth) {
        let s = String(fullText || '').trim();
        const node = textSel.node();
        if (!node || maxWidth <= 4) {
            textSel.text('');
            return;
        }
        textSel.text(s);
        if (node.getComputedTextLength() <= maxWidth) return;
        while (s.length > 1) {
            s = s.slice(0, -1);
            textSel.text(`${s}…`);
            if (node.getComputedTextLength() <= maxWidth) return;
        }
        textSel.text('…');
    }

    function nodeTotalWidth(nodeData, nodeW, urls) {
        const level = nodeData.level || 'item';
        const { w } = pillSize(level, !!nodeData.subtitle, nodeW);
        return w + actionStripWidth(buildActions(nodeData, urls));
    }

    const LINK = { radius: 8, minGap: 28 };

    function targetAnchorX(nodeData) {
        const level = nodeData.level || 'item';
        if (level === 'position') return 16;
        if (level === 'employee') return 6;
        return 2;
    }

    function linkSourceLevel(d) {
        return d.source.data.level || 'item';
    }

    function linkClass(d) {
        return `jp-org-tree-link--from-${linkSourceLevel(d)}`;
    }

    /** Đường vuông góc bo góc — tránh path lỗi khi khoảng cách ngắn. */
    function roundedLinkPath(d, nodeW, urls) {
        const sx = d.source.y + nodeTotalWidth(d.source.data, nodeW, urls);
        const sy = d.source.x;
        const tx = d.target.y + targetAnchorX(d.target.data);
        const ty = d.target.x;
        const dx = tx - sx;
        const dy = ty - sy;

        if (dx <= 4) {
            return `M${sx},${sy}L${tx},${ty}`;
        }
        if (Math.abs(dy) < 1) {
            return `M${sx},${sy}H${tx}`;
        }

        let mx = sx + Math.min(Math.max(dx * 0.42, 20), dx - 14);
        mx = Math.max(sx + 8, Math.min(tx - 8, mx));

        const r = Math.min(
            LINK.radius,
            (mx - sx) / 2,
            (tx - mx) / 2,
            Math.abs(dy) / 2,
        );

        if (r < 2 || dx < LINK.minGap) {
            return `M${sx},${sy}H${mx}V${ty}H${tx}`;
        }

        const vDir = dy > 0 ? 1 : -1;
        return [
            `M${sx},${sy}`,
            `H${mx - r}`,
            `Q${mx},${sy} ${mx},${sy + vDir * r}`,
            `V${ty - vDir * r}`,
            `Q${mx},${ty} ${mx + r},${ty}`,
            `H${tx}`,
        ].join(' ');
    }

    function fillUrl(tpl, vals) {
        let u = tpl || '';
        Object.entries(vals).forEach(([key, val]) => {
            u = u.split(`{${key}}`).join(encodeURIComponent(String(val ?? '')));
        });
        return u;
    }

    function positionKey(nodeData) {
        return nodeData.position_key
            || `div:${nodeData.division_id}:pos:${nodeData.name}`;
    }

    function collectPositionKeys(node, keys) {
        if (node.level === 'position' && node.position_key) {
            keys.add(node.position_key);
        }
        (node.children || []).forEach((c) => collectPositionKeys(c, keys));
    }

    function cloneWithCollapse(tree, collapsed) {
        const copy = JSON.parse(JSON.stringify(tree));
        function walk(n) {
            if (n.level === 'position' && collapsed.has(n.position_key)) {
                n.children = [];
            } else {
                (n.children || []).forEach(walk);
            }
        }
        walk(copy);
        return copy;
    }

    function primaryHref(nodeData, urls) {
        const level = nodeData.level;
        const id = nodeData.id;
        if (level === 'employee' && (nodeData.user_id || id) && urls.userEdit) {
            return urls.userEdit.replace('{id}', String(nodeData.user_id || id));
        }
        if (level === 'department' && id && urls.deptEdit) {
            return urls.deptEdit.replace('{id}', String(id));
        }
        if (level === 'division' && id && urls.divEdit) {
            return urls.divEdit.replace('{id}', String(id));
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
            if (id && urls.positionEdit) {
                out.push({ href: urls.positionEdit.replace('{id}', String(id)), title: 'Sửa danh mục vị trí', glyph: '✎' });
            }
            if (id && urls.positionDelete) {
                out.push({ href: urls.positionDelete.replace('{id}', String(id)), title: 'Xóa vị trí', glyph: '×', danger: true });
            }
        }

        return out;
    }

    function columnPositions(nodes, nodeW) {
        const colX = new Map();
        const colW = new Map();
        nodes.forEach((n) => {
            const cur = colX.get(n.depth);
            const pw = pillSize(n.data.level || 'item', !!n.data.subtitle, nodeW).w;
            if (cur === undefined || n.y < cur) {
                colX.set(n.depth, n.y);
            }
            colW.set(n.depth, Math.max(colW.get(n.depth) || 0, pw, nodeW - 8));
        });
        return COLUMN_LABELS.map((label, depth) => ({
            label,
            depth,
            x: colX.has(depth) ? colX.get(depth) : depth * nodeW,
            w: colW.get(depth) || nodeW - 4,
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
            trackEl.appendChild(el);
        });
    }

    function syncHeaderColumns(trackEl, columns, marginLeft, transform) {
        if (!trackEl || !columns || !columns.length) return;
        trackEl.style.transform = 'none';
        const headerFs = Math.round(11 * Math.min(1.25, Math.max(0.8, transform.k)));
        const labels = trackEl.querySelectorAll('.jp-org-chart-col-label');
        columns.forEach((col, i) => {
            const el = labels[i];
            if (!el) return;
            const left = transform.x + transform.k * (marginLeft + col.x);
            el.style.left = `${left}px`;
            el.style.width = `${transform.k * col.w}px`;
            el.style.fontSize = `${headerFs}px`;
        });
    }

    function clampTransform(transform) {
        const k = Math.max(ZOOM.min, Math.min(ZOOM.max, transform.k));
        if (k === transform.k) return transform;
        return d3.zoomIdentity.translate(transform.x, transform.y).scale(k);
    }

    function applySyncedTransform(trackEl, zoomRoot, transform) {
        transform = clampTransform(transform);
        zoomRoot.attr('transform', transform);
        chartState.savedTransform = transform;
        const sync = chartState.headerSync;
        if (sync) {
            syncHeaderColumns(trackEl || sync.trackEl, sync.columns, sync.marginLeft, transform);
        }
    }

    function scheduleZoomApply(trackEl, zoomRoot, transform) {
        chartState.pendingTransform = transform;
        if (chartState.zoomRaf) return;
        chartState.zoomRaf = requestAnimationFrame(() => {
            chartState.zoomRaf = null;
            applySyncedTransform(trackEl, zoomRoot, chartState.pendingTransform);
        });
    }

    function togglePosition(key) {
        if (chartState.collapsed.has(key)) {
            chartState.collapsed.delete(key);
        } else {
            chartState.collapsed.add(key);
        }
        window.jpOrgTreeInit();
    }

    function renderChart(mount, headerTrack, data, urls) {
        const margin = { top: 16, right: LAYOUT.chartPadRight, bottom: 20, left: 20 };
        const vp = document.getElementById('jp-org-chart-viewport');
        const vpW = (vp && vp.clientWidth) || mount.clientWidth || 1200;

        const root = d3.hierarchy(data);
        const maxDepth = d3.max(root.descendants(), (d) => d.depth) ?? 4;
        const nodeW = resolveNodeW(vpW, maxDepth);
        const treeLayout = d3.tree()
            .nodeSize([LAYOUT.nodeH, nodeW])
            .separation((a, b) => {
                const eh = a.data.level === 'employee' || b.data.level === 'employee';
                return a.parent === b.parent ? (eh ? 0.92 : 1) : 1.05;
            });
        treeLayout(root);

        const nodes = root.descendants();
        const links = root.links();
        const columns = columnPositions(nodes, nodeW);
        renderHtmlHeaders(headerTrack, columns, margin.left);

        const yMin = d3.min(nodes, (d) => d.x) ?? 0;
        const yMax = d3.max(nodes, (d) => d.x) ?? 0;
        const contentRight = nodeContentRight(nodes, nodeW, urls);
        const maxPillH = d3.max(nodes, (d) => pillSize(d.data.level || 'item', !!d.data.subtitle, nodeW).h)
            ?? LAYOUT.nodeH;
        const innerH = yMax - yMin + maxPillH;
        const chartW = contentRight + 32;
        const svgW = chartW + margin.left + margin.right;
        const svgH = innerH + margin.top + margin.bottom;

        const svg = d3.select(mount)
            .append('svg')
            .attr('class', 'jp-org-tree-svg')
            .attr('width', svgW)
            .attr('height', svgH);

        const defs = svg.append('defs');
        const rootGrad = defs.append('linearGradient')
            .attr('id', 'jp-org-root-grad')
            .attr('x1', '0%')
            .attr('y1', '0%')
            .attr('x2', '100%')
            .attr('y2', '100%');
        rootGrad.append('stop').attr('offset', '0%').attr('stop-color', '#b91c1c');
        rootGrad.append('stop').attr('offset', '100%').attr('stop-color', '#dc2626');

        const zoomRoot = svg.append('g').attr('class', 'jp-org-tree-zoom');
        zoomRoot.append('rect')
            .attr('class', 'jp-org-tree-pan-surface')
            .attr('width', svgW)
            .attr('height', svgH)
            .attr('fill', 'transparent');

        const g = zoomRoot.append('g')
            .attr('class', 'jp-org-tree-chart')
            .attr('transform', `translate(${margin.left},${margin.top - yMin})`);

        g.append('g')
            .attr('class', 'jp-org-tree-col-bands')
            .selectAll('rect')
            .data(columns)
            .join('rect')
            .attr('class', (_, i) => `jp-org-tree-col-band jp-org-tree-col-band--${i}`)
            .attr('x', (d) => d.x)
            .attr('y', -12)
            .attr('width', (d) => d.w)
            .attr('height', innerH + 24)
            .attr('rx', 10);

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

        const linkG = g.append('g').attr('class', 'jp-org-tree-links');
        const linkPath = (d) => roundedLinkPath(d, nodeW, urls);

        linkG.selectAll('path.jp-org-tree-link')
            .data(links)
            .join('path')
            .attr('class', (d) => `jp-org-tree-link ${linkClass(d)}`)
            .attr('fill', 'none')
            .attr('d', linkPath);

        const nodeG = g.append('g')
            .attr('class', 'jp-org-tree-nodes')
            .selectAll('g')
            .data(nodes)
            .join('g')
            .attr('class', (d) => {
                const lvl = d.data.level || 'item';
                const expanded = lvl === 'position' && !chartState.collapsed.has(positionKey(d.data));
                let cls = `jp-org-tree-node jp-org-tree-node--${lvl}`;
                if (primaryHref(d.data, urls)) cls += ' is-clickable';
                if (lvl === 'position') cls += expanded ? ' is-expanded' : ' is-collapsed';
                return cls;
            })
            .attr('transform', (d) => `translate(${d.y},${d.x})`);

        nodeG.each(function (d) {
            const sel = d3.select(this);
            const level = d.data.level || 'item';
            const hasSub = !!d.data.subtitle;
            const { w: pillW, h: pillH } = pillSize(level, hasSub, nodeW);
            const href = primaryHref(d.data, urls);
            const actions = buildActions(d.data, urls);
            const isPosition = level === 'position';
            const pKey = isPosition ? positionKey(d.data) : '';
            const expanded = isPosition && !chartState.collapsed.has(pKey);

            const pill = sel.append('g').attr('class', 'jp-org-tree-pill');

            const pillStroke = level === 'root' ? 2 : level === 'position' && expanded ? 2 : 1.5;
            const chevW = isPosition ? 18 : 0;
            const actW = actionStripWidth(actions);
            const badgeW = level !== 'employee' ? 30 : 0;
            const innerPillW = pillW + actW;
            const pillX = chevW;
            const labelX = chevW + 12;
            const badgeX = innerPillW - actW - badgeW - 8;
            const labelMaxW = Math.max(24, badgeX - labelX - 6);

            if (isPosition) {
                pill.append('text')
                    .attr('class', 'jp-org-tree-expand-icon')
                    .attr('x', 6)
                    .attr('y', 5)
                    .text(expanded ? '▼' : '▶');
            }

            pill.append('rect')
                .attr('class', 'jp-org-tree-pill-rect')
                .attr('x', pillX)
                .attr('y', -pillH / 2)
                .attr('width', innerPillW - pillX)
                .attr('height', pillH)
                .attr('rx', PILL_RX)
                .attr('ry', PILL_RX);
            if (pillStroke > 1.5) {
                pill.select('.jp-org-tree-pill-rect').attr('stroke-width', pillStroke);
            }

            if (isPosition) {
                pill.style('cursor', 'pointer').on('click', (ev) => {
                    if (ev.defaultPrevented) return;
                    togglePosition(pKey);
                });
            } else if (href) {
                pill.style('cursor', 'pointer').on('click', (ev) => {
                    if (ev.defaultPrevented) return;
                    window.location.href = href;
                });
            }

            const labelSel = pill.append('text')
                .attr('class', 'jp-org-tree-pill-label')
                .attr('x', labelX)
                .attr('y', hasSub ? -2 : 5);
            ellipsizeSvgText(labelSel, d.data.name, labelMaxW);

            if (d.data.subtitle) {
                const subSel = pill.append('text')
                    .attr('class', 'jp-org-tree-pill-sub')
                    .attr('x', labelX)
                    .attr('y', 14);
                ellipsizeSvgText(subSel, d.data.subtitle, labelMaxW);
            }

            if (level !== 'employee') {
                const badgeH = 22;
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
            }

            if (actions.length) {
                const menuX = innerPillW - actW + 2;
                const menuY = -ACTION.size / 2;
                const menu = pill.append('g')
                    .attr('class', 'jp-org-tree-actions')
                    .attr('transform', `translate(${menuX},${menuY})`);
                actions.forEach((act, i) => {
                    const step = ACTION.size + ACTION.gap;
                    const ag = menu.append('g').attr('transform', `translate(${i * step},0)`);
                    const link = ag.append('a')
                        .attr('href', act.href)
                        .attr('class', `jp-org-tree-action-link${act.danger ? ' is-danger' : ''}`)
                        .attr('title', act.title)
                        .attr('aria-label', act.title)
                        .on('click', (ev) => ev.stopPropagation());
                    link.append('rect')
                        .attr('class', 'jp-org-tree-action-bg')
                        .attr('width', ACTION.size)
                        .attr('height', ACTION.size)
                        .attr('rx', 5);
                    link.append('text')
                        .attr('class', 'jp-org-tree-action-icon')
                        .attr('x', ACTION.size / 2)
                        .attr('y', ACTION.size - 6)
                        .attr('text-anchor', 'middle')
                        .text(act.glyph);
                });
            }

            const hint = level === 'employee'
                ? `${d.data.name}${d.data.subtitle ? ` (${d.data.subtitle})` : ''}`
                : `${d.data.name} — ${d.data.count ?? 0} NV`;
            pill.append('title').text(isPosition ? `${hint} — bấm để ${expanded ? 'đóng' : 'mở'} danh sách NV` : hint);
        });

        chartState.headerSync = {
            trackEl: headerTrack,
            columns,
            marginLeft: margin.left,
        };

        const zoom = d3.zoom()
            .scaleExtent([ZOOM.min, ZOOM.max])
            .wheelDelta((event) => {
                const mode = event.deltaMode;
                const scale = mode === 1 ? 0.05 : mode ? 1 : ZOOM.wheelFactor;
                return -event.deltaY * scale;
            })
            .filter((event) => {
                if (event.type === 'wheel') return true;
                if (event.type === 'dblclick') return false;
                const t = event.target;
                if (t && t.closest && t.closest('.jp-org-tree-action-link')) return false;
                return true;
            })
            .on('zoom', (event) => scheduleZoomApply(headerTrack, zoomRoot, event.transform));

        svg.call(zoom).on('dblclick.zoom', null);

        if (headerTrack) headerTrack.style.minWidth = `${svgW}px`;
        if (vp) vp.classList.toggle('jp-org-chart-viewport--wide', svgW > vpW);

        const fitScale = svgW > vpW
            ? Math.max(ZOOM.min, Math.min(ZOOM.max, (vpW - 32) / svgW))
            : 1;
        let initial = chartState.savedTransform
            || d3.zoomIdentity.translate(12, 8).scale(fitScale);
        if (initial.k < ZOOM.min) initial = d3.zoomIdentity.translate(initial.x, initial.y).scale(ZOOM.min);
        if (initial.k > ZOOM.max) initial = d3.zoomIdentity.translate(initial.x, initial.y).scale(ZOOM.max);
        svg.call(zoom.transform, initial);
        applySyncedTransform(headerTrack, zoomRoot, initial);

        mount.classList.add('jp-org-tree-mount--ready');
    }

    window.jpOrgTreeInit = function jpOrgTreeInit() {
        const mount = document.getElementById('jp-org-tree-mount');
        const headerTrack = document.getElementById('jp-org-headers-track');
        if (!mount) return;

        if (typeof d3 === 'undefined') {
            showError(mount, 'Không tải được thư viện D3.');
            return;
        }
        if (!window.JP_ORG_TREE) {
            showError(mount, 'Không có dữ liệu sơ đồ.');
            return;
        }

        if (!chartState.fullData) {
            chartState.fullData = JSON.parse(JSON.stringify(window.JP_ORG_TREE));
            const keys = new Set();
            collectPositionKeys(chartState.fullData, keys);
            chartState.collapsed = keys;
        }
        chartState.urls = window.JP_ORG_URLS || {};

        mount.innerHTML = '';
        const data = cloneWithCollapse(chartState.fullData, chartState.collapsed);
        renderChart(mount, headerTrack, data, chartState.urls);
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
        chartState.fullData = null;
        window.jpOrgTreeInit();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot);
    } else {
        boot();
    }
})();
