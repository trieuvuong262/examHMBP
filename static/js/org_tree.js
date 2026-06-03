/**
 * Sơ đồ cây ngang — Công ty → Phòng ban → Bộ phận → Vị trí (D3).
 * Kéo / zoom; đường vuông góc; bấm ô để sửa.
 */
(function () {
    'use strict';

    const PILL_RX = 6;
    const NODE_H = 54;
    const NODE_W = 228;
    const HEADER_H = 32;
    const COLUMN_LABELS = ['Tổng / GĐĐH', 'Phòng ban', 'Bộ phận', 'Vị trí'];

    function showError(mount, msg) {
        mount.innerHTML = `<div class="alert alert-warning m-3">${msg}</div>`;
    }

    function pillSize(level, hasSubtitle) {
        if (level === 'root') {
            return { w: 228, h: hasSubtitle ? 50 : 40 };
        }
        if (level === 'department') {
            return { w: 210, h: 40 };
        }
        if (level === 'position') {
            return { w: 188, h: 34 };
        }
        return { w: 200, h: 38 };
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
                out.push({
                    href: urls.divisionAdd.replace('{dept_id}', String(id)),
                    icon: 'bi-plus-lg',
                    title: 'Thêm bộ phận',
                });
            }
            if (urls.deptPermissions) {
                out.push({
                    href: urls.deptPermissions.replace('{id}', String(id)),
                    icon: 'bi-shield-lock',
                    title: 'Phân quyền',
                });
            }
            if (urls.deptEdit) {
                out.push({
                    href: urls.deptEdit.replace('{id}', String(id)),
                    icon: 'bi-pencil-square',
                    title: 'Sửa phòng ban',
                });
            }
            if (urls.deptDelete) {
                out.push({
                    href: urls.deptDelete.replace('{id}', String(id)),
                    icon: 'bi-trash',
                    title: 'Xóa',
                    danger: true,
                });
            }
        }

        if (level === 'division' && id) {
            if (urls.positionAdd) {
                out.push({
                    href: fillUrl(urls.positionAdd, {
                        dept_id: deptId || '',
                        div_id: id,
                    }),
                    icon: 'bi-plus-lg',
                    title: 'Thêm vị trí',
                });
            }
            if (urls.divEdit) {
                out.push({
                    href: urls.divEdit.replace('{id}', String(id)),
                    icon: 'bi-pencil-square',
                    title: 'Sửa bộ phận',
                });
            }
            if (urls.divDelete) {
                out.push({
                    href: urls.divDelete.replace('{id}', String(id)),
                    icon: 'bi-trash',
                    title: 'Xóa',
                    danger: true,
                });
            }
        }

        if (level === 'position') {
            if (id && urls.positionEdit) {
                out.push({
                    href: urls.positionEdit.replace('{id}', String(id)),
                    icon: 'bi-pencil-square',
                    title: 'Sửa vị trí',
                });
            }
            if (id && urls.positionDelete) {
                out.push({
                    href: urls.positionDelete.replace('{id}', String(id)),
                    icon: 'bi-trash',
                    title: 'Xóa vị trí',
                    danger: true,
                });
            }
            if (urls.userAdd && divId) {
                out.push({
                    href: fillUrl(urls.userAdd, {
                        dept_id: deptId || '',
                        div_id: divId,
                        position: nodeData.name || '',
                    }),
                    icon: 'bi-person-plus',
                    title: 'Thêm nhân viên',
                });
            }
        }

        if (level === 'root' && urls.userList) {
            out.push({
                href: urls.userList,
                icon: 'bi-people',
                title: 'Nhân sự',
            });
        }

        return out;
    }

    function actionGlyph(biClass) {
        if (biClass === 'bi-plus-lg') return '+';
        if (biClass === 'bi-trash') return '×';
        if (biClass === 'bi-shield-lock') return '◆';
        if (biClass === 'bi-people') return 'NS';
        if (biClass === 'bi-person-plus') return '+';
        return '✎';
    }

    function drawColumnHeaders(headerG, nodes) {
        const colX = new Map();
        nodes.forEach((n) => {
            const cur = colX.get(n.depth);
            if (cur === undefined || n.y < cur) {
                colX.set(n.depth, n.y);
            }
        });

        COLUMN_LABELS.forEach((label, depth) => {
            const x = colX.has(depth) ? colX.get(depth) : depth * NODE_W;
            const w = NODE_W - 12;
            headerG.append('rect')
                .attr('class', 'jp-org-tree-col-head-bg')
                .attr('x', x)
                .attr('y', -HEADER_H + 4)
                .attr('width', w)
                .attr('height', HEADER_H - 8)
                .attr('rx', 4);
            headerG.append('text')
                .attr('class', 'jp-org-tree-col-head-label')
                .attr('x', x + w / 2)
                .attr('y', -HEADER_H / 2 + 4)
                .attr('text-anchor', 'middle')
                .text(label);
        });
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
        const margin = { top: HEADER_H + 8, right: 32, bottom: 12, left: 12 };

        const root = d3.hierarchy(data);
        d3.tree()
            .nodeSize([NODE_H, NODE_W])
            .separation((a, b) => (a.parent === b.parent ? 1 : 1.08))(root);

        const nodes = root.descendants();
        const links = root.links();
        const yMin = d3.min(nodes, (d) => d.x) ?? 0;
        const yMax = d3.max(nodes, (d) => d.x) ?? 0;
        const xMax = d3.max(nodes, (d) => d.y) ?? 0;
        const maxPillH = d3.max(nodes, (d) => pillSize(d.data.level || 'item', !!d.data.subtitle).h) ?? NODE_H;
        const innerH = yMax - yMin + maxPillH;
        const chartW = xMax + 48;
        const chartH = innerH;
        const svgW = chartW + margin.left + margin.right;
        const svgH = chartH + margin.top + margin.bottom;

        const svg = d3.select(mount)
            .append('svg')
            .attr('class', 'jp-org-tree-svg')
            .attr('width', '100%')
            .attr('height', Math.max(420, Math.min(svgH, 720)))
            .attr('viewBox', `0 0 ${svgW} ${svgH}`)
            .attr('preserveAspectRatio', 'xMinYMin meet');

        const zoomRoot = svg.append('g').attr('class', 'jp-org-tree-zoom');
        const g = zoomRoot.append('g')
            .attr('transform', `translate(${margin.left},${margin.top - yMin})`);

        const headerG = g.append('g').attr('class', 'jp-org-tree-headers');
        drawColumnHeaders(headerG, nodes);

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
            const pill = sel.append('g').attr('class', 'jp-org-tree-pill');

            function appendPillRect(parent) {
                parent.append('rect')
                    .attr('class', 'jp-org-tree-pill-rect')
                    .attr('x', 0)
                    .attr('y', -pillH / 2)
                    .attr('width', pillW)
                    .attr('height', pillH)
                    .attr('rx', PILL_RX)
                    .attr('ry', PILL_RX);
            }

            if (href) {
                const link = pill.append('a')
                    .attr('href', href)
                    .attr('class', 'jp-org-tree-pill-hit')
                    .attr('aria-label', `Mở: ${d.data.name}`);
                appendPillRect(link);
            } else {
                appendPillRect(pill);
            }

            pill.append('text')
                .attr('class', 'jp-org-tree-pill-label')
                .attr('x', 10)
                .attr('y', hasSub ? -2 : 4)
                .text(truncate(d.data.name, 26));

            if (d.data.subtitle) {
                pill.append('text')
                    .attr('class', 'jp-org-tree-pill-sub')
                    .attr('x', 10)
                    .attr('y', 12)
                    .text(truncate(d.data.subtitle, 28));
            }

            const badgeW = 26;
            const badgeH = 20;
            const badgeX = pillW - badgeW - 6;
            pill.append('rect')
                .attr('class', 'jp-org-tree-pill-badge-bg')
                .attr('x', badgeX)
                .attr('y', -badgeH / 2)
                .attr('width', badgeW)
                .attr('height', badgeH)
                .attr('rx', 4)
                .attr('ry', 4);

            pill.append('text')
                .attr('class', 'jp-org-tree-pill-badge-txt')
                .attr('x', badgeX + badgeW / 2)
                .attr('y', 4)
                .attr('text-anchor', 'middle')
                .text(String(d.data.count ?? 0));

            if (actions.length) {
                const menu = sel.append('g')
                    .attr('class', 'jp-org-tree-actions')
                    .attr('transform', `translate(${pillW - 2},${-pillH / 2 - 2})`);

                actions.forEach((act, i) => {
                    const ag = menu.append('g')
                        .attr('class', 'jp-org-tree-action')
                        .attr('transform', `translate(${i * 20},0)`);

                    const link = ag.append('a')
                        .attr('href', act.href)
                        .attr('class', `jp-org-tree-action-link${act.danger ? ' is-danger' : ''}`)
                        .attr('title', act.title)
                        .attr('aria-label', act.title)
                        .on('click', (ev) => ev.stopPropagation());

                    link.append('rect')
                        .attr('class', 'jp-org-tree-action-bg')
                        .attr('x', 0)
                        .attr('y', 0)
                        .attr('width', 18)
                        .attr('height', 18)
                        .attr('rx', 3);
                    link.append('text')
                        .attr('class', 'jp-org-tree-action-icon')
                        .attr('x', 9)
                        .attr('y', 13)
                        .attr('text-anchor', 'middle')
                        .text(actionGlyph(act.icon));
                });
            }

            pill.append('title').text(`${d.data.name} — ${d.data.count ?? 0} NV`);
        });

        const zoom = d3.zoom()
            .scaleExtent([0.45, 2.2])
            .filter((event) => {
                if (event.type === 'wheel') return true;
                if (event.button === 0) return true;
                return !event.ctrlKey && !event.button;
            })
            .on('zoom', (event) => {
                zoomRoot.attr('transform', event.transform);
            });

        svg.call(zoom).on('dblclick.zoom', null);

        const fitScale = Math.min(1, (mount.clientWidth || 900) / svgW);
        const initial = d3.zoomIdentity.translate(8, 8).scale(Math.max(0.65, fitScale));
        svg.call(zoom.transform, initial);

        mount.classList.add('jp-org-tree-mount--pan');
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
