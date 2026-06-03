/**
 * Sơ đồ cây cơ cấu tổ chức (D3) — ngang trái → phải.
 */
(function () {
    'use strict';

    const mount = document.getElementById('jp-org-tree-mount');
    if (!mount || !window.JP_ORG_TREE) return;

    const data = window.JP_ORG_TREE;
    const urls = window.JP_ORG_URLS || {};

    const width = Math.max(mount.clientWidth || 900, 720);
    const nodeX = 240;
    const nodeY = 44;
    const margin = { top: 24, right: 40, bottom: 24, left: 16 };

    const root = d3.hierarchy(data);
    const tree = d3.tree().nodeSize([nodeY, nodeX]);
    tree(root);

    const nodes = root.descendants();
    const links = root.links();

    const yMin = d3.min(nodes, (d) => d.x) ?? 0;
    const yMax = d3.max(nodes, (d) => d.x) ?? 0;
    const xMax = d3.max(nodes, (d) => d.y) ?? 0;
    const height = yMax - yMin + nodeY + margin.top + margin.bottom;
    const svgWidth = xMax + margin.left + margin.right + 120;

    const svg = d3.select(mount)
        .append('svg')
        .attr('width', svgWidth)
        .attr('height', height)
        .attr('class', 'jp-org-tree-svg');

    const g = svg.append('g')
        .attr('transform', `translate(${margin.left},${margin.top - yMin})`);

    g.selectAll('.jp-org-tree-link')
        .data(links)
        .join('path')
        .attr('class', 'jp-org-tree-link')
        .attr('fill', 'none')
        .attr('d', d3.linkHorizontal()
            .x((d) => d.y)
            .y((d) => d.x));

    const node = g.selectAll('.jp-org-tree-node')
        .data(nodes)
        .join('g')
        .attr('class', (d) => `jp-org-tree-node jp-org-tree-node--${d.data.level || 'item'}`)
        .attr('transform', (d) => `translate(${d.y},${d.x})`);

    node.each(function (d) {
        const fo = d3.select(this)
            .append('foreignObject')
            .attr('x', 0)
            .attr('y', -18)
            .attr('width', 210)
            .attr('height', 52)
            .attr('class', 'jp-org-tree-fo');

        const div = fo.append('xhtml:div')
            .attr('class', 'jp-org-tree-pill');

        const info = div.append('div').attr('class', 'jp-org-tree-pill__body');
        info.append('div').attr('class', 'jp-org-tree-pill__name').text(truncate(d.data.name, 42));
        if (d.data.subtitle) {
            info.append('div').attr('class', 'jp-org-tree-pill__sub').text(d.data.subtitle);
        }

        div.append('div')
            .attr('class', 'jp-org-tree-pill__badge')
            .text(String(d.data.count ?? 0));

        const actions = buildActions(d.data);
        if (actions.length) {
            const menu = div.append('div').attr('class', 'jp-org-tree-pill__menu');
            actions.forEach((a) => {
                menu.append('a')
                    .attr('href', a.href)
                    .attr('class', `jp-org-tree-pill__action ${a.danger ? 'is-danger' : ''}`)
                    .attr('title', a.title)
                    .html(`<i class="bi ${a.icon}"></i>`);
            });
        }
    });

    mount.style.minHeight = `${height}px`;

    function truncate(text, max) {
        const s = String(text || '');
        return s.length > max ? `${s.slice(0, max - 1)}…` : s;
    }

    function buildActions(nodeData) {
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
            if (deptId && urls.divisionAdd) {
                out.push({
                    href: urls.divisionAdd.replace('{dept_id}', String(deptId)),
                    icon: 'bi-building',
                    title: 'Phòng ban',
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
})();
