/**
 * Sơ đồ cây ngang — Công ty → Phòng ban → Bộ phận → Vị trí (D3).
 * Đường nối vuông góc; bấm nút → form sửa (giữ quản lý qua bảng bên dưới).
 */
(function () {
    'use strict';

    function showError(mount, msg) {
        mount.innerHTML = `<div class="alert alert-warning m-3">${msg}</div>`;
    }

    function pillSize(level, hasSubtitle) {
        const h = hasSubtitle ? 46 : 36;
        if (level === 'root') return { w: 200, h };
        if (level === 'department') return { w: 190, h };
        if (level === 'position') return { w: 165, h: 34 };
        return { w: 175, h };
    }

    /** Đường nối vuông góc: ra phải từ nút cha → xuống/lên → vào nút con. */
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

    function primaryHref(nodeData, urls) {
        const level = nodeData.level;
        const id = nodeData.id;
        if (level === 'department' && id && urls.deptEdit) {
            return urls.deptEdit.replace('{id}', String(id));
        }
        if (level === 'division' && id && urls.divEdit) {
            return urls.divEdit.replace('{id}', String(id));
        }
        if (level === 'root' && urls.userList) {
            return urls.userList;
        }
        if (level === 'position' && urls.userList) {
            const q = encodeURIComponent(nodeData.name || '');
            return `${urls.userList}?q=${q}`;
        }
        return null;
    }

    function buildActions(nodeData, urls) {
        const level = nodeData.level;
        const id = nodeData.id;
        const deptId = nodeData.dept_id;
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
                    primary: true,
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
            if (urls.divEdit) {
                out.push({
                    href: urls.divEdit.replace('{id}', String(id)),
                    icon: 'bi-pencil-square',
                    title: 'Sửa bộ phận',
                    primary: true,
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

        if (level === 'root' && urls.userList) {
            out.push({
                href: urls.userList,
                icon: 'bi-people',
                title: 'Nhân sự',
            });
        }

        return out;
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
        const svgW = xMax + margin.left + margin.right + 120;
        const svgH = innerH + margin.top + margin.bottom;

        const svg = d3.select(mount)
            .append('svg')
            .attr('class', 'jp-org-tree-svg')
            .attr('width', svgW)
            .attr('height', svgH)
            .attr('viewBox', `0 0 ${svgW} ${svgH}`);

        const g = svg.append('g')
            .attr('transform', `translate(${margin.left},${margin.top - yMin})`);

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
            const rx = pillH / 2;
            const href = primaryHref(d.data, urls);
            const actions = buildActions(d.data, urls);

            const pill = sel.append('g').attr('class', 'jp-org-tree-pill');

            if (href) {
                pill.append('a')
                    .attr('href', href)
                    .attr('class', 'jp-org-tree-pill-hit')
                    .attr('aria-label', `Mở: ${d.data.name}`)
                    .append('rect')
                    .attr('class', 'jp-org-tree-pill-rect')
                    .attr('x', 0)
                    .attr('y', -pillH / 2)
                    .attr('width', pillW)
                    .attr('height', pillH)
                    .attr('rx', rx)
                    .attr('ry', rx);
            } else {
                pill.append('rect')
                    .attr('class', 'jp-org-tree-pill-rect')
                    .attr('x', 0)
                    .attr('y', -pillH / 2)
                    .attr('width', pillW)
                    .attr('height', pillH)
                    .attr('rx', rx)
                    .attr('ry', rx);
            }

            pill.append('text')
                .attr('class', 'jp-org-tree-pill-label')
                .attr('x', 12)
                .attr('y', hasSub ? -4 : 4)
                .text(truncate(d.data.name, 28));

            if (d.data.subtitle) {
                pill.append('text')
                    .attr('class', 'jp-org-tree-pill-sub')
                    .attr('x', 12)
                    .attr('y', 12)
                    .text(truncate(d.data.subtitle, 32));
            }

            const badgeX = pillW - 8;
            pill.append('circle')
                .attr('class', 'jp-org-tree-pill-badge-bg')
                .attr('cx', badgeX)
                .attr('cy', 0)
                .attr('r', 14);

            pill.append('text')
                .attr('class', 'jp-org-tree-pill-badge-txt')
                .attr('x', badgeX)
                .attr('y', 4)
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
                        .attr('x', 0)
                        .attr('y', 0)
                        .attr('width', 20)
                        .attr('height', 20)
                        .attr('rx', 4);
                    link.append('text')
                        .attr('class', 'jp-org-tree-action-icon')
                        .attr('x', 10)
                        .attr('y', 14)
                        .attr('text-anchor', 'middle')
                        .text(actionGlyph(act.icon));
                });
            }

            pill.append('title').text(`${d.data.name} — ${d.data.count ?? 0} NV`);
        });

        mount.style.minHeight = `${Math.min(svgH, 640)}px`;
    };

    function actionGlyph(biClass) {
        if (biClass === 'bi-plus-lg') return '+';
        if (biClass === 'bi-trash') return '×';
        if (biClass === 'bi-shield-lock') return '◆';
        if (biClass === 'bi-people') return 'NS';
        return '✎';
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
