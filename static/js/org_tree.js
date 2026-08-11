/**
 * Sơ đồ cây ngang — Công ty → PB → BP → Vị trí → Nhân viên (ẩn/mở).
 */
(function () {
    'use strict';

    /** Khoảng cách ngang giữa các cột. */
    const WIDTH_SCALE = 1.75;
    /** Chừa chỗ cho mũi tên Vị trí → NV trong ô Vị trí. */
    const LINK_GAP_RESERVE = 48;
    /** Đẩy cột NV thêm so với layout cây (tỷ lệ nodeW + gap cố định). */
    const EMPLOYEE_X_NUDGE = 0.28;
    const POSITION_EMPLOYEE_EXTRA_GAP = 48;
    /** Số NV tối đa hiển thị trên sơ đồ khi mở vị trí (khớp backend). */
    const EMPLOYEE_PREVIEW_MAX = 8;

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

    function isExpandableLevel(level) {
        return level === 'position';
    }

    const ZOOM = {
        min: 0.78,
        max: 1.85,
        wheelFactor: 0.00055,
    };

    const ACTION = { size: 22, gap: 2 };
    /** Gán trưởng phòng / trưởng BP / giám đốc — khác nút + thêm danh mục. */
    const HEAD_ASSIGN_GLYPH = '★';

    const chartState = {
        collapsed: new Set(),
        showAllEmployees: false,
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
            return { w: Math.round(Math.min(200, Math.max(130, nodeW * 0.38)) * s), h: 32 };
        }
        if (level === 'root') {
            return { w: Math.round((200 + gap * 0.5) * s), h: hasSubtitle ? 52 : 42 };
        }
        if (level === 'department') {
            return { w: Math.round((188 + gap * 0.45) * s), h: hasSubtitle ? 52 : 44 };
        }
        if (level === 'division') {
            return { w: Math.round((178 + gap * 0.5) * s), h: hasSubtitle ? 52 : 40 };
        }
        if (level === 'position') {
            const raw = Math.round(Math.max(nodeW - 12, 220 + gap * 0.7) * s);
            const maxW = Math.round((nodeW - LINK_GAP_RESERVE) * s);
            return { w: Math.min(raw, maxW), h: 40 };
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
            const chevron = isExpandableLevel(level) ? 18 : 0;
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
        let total = w + actionStripWidth(buildActions(nodeData, urls));
        if (isExpandableLevel(level)) total += 18;
        return total;
    }

    function nudgeEmployeeColumn(nodes, nodeW) {
        const extra = Math.round(
            nodeW * EMPLOYEE_X_NUDGE + POSITION_EMPLOYEE_EXTRA_GAP * WIDTH_SCALE,
        );
        if (extra <= 0) return;
        nodes.forEach((n) => {
            if ((n.data.level || '') === 'employee') {
                n.y += extra;
            }
        });
    }

    const LINK = {
        radius: Math.round(8 * WIDTH_SCALE),
        minGap: Math.round(28 * WIDTH_SCALE),
        stubMin: Math.round(20 * WIDTH_SCALE),
        stubEnd: Math.round(14 * WIDTH_SCALE),
    };

    function targetAnchorX(nodeData, nodeW) {
        const level = nodeData.level || 'item';
        if (isExpandableLevel(level)) return 16;
        if (level === 'employee') {
            const { w } = pillSize('employee', !!nodeData.subtitle, nodeW);
            return Math.max(5, Math.round(w * 0.06));
        }
        return 2;
    }

    function linkSourceLevel(d) {
        return d.source.data.level || 'item';
    }

    function linkClass(d) {
        const from = linkSourceLevel(d);
        const to = d.target.data.level || 'item';
        let cls = `jp-org-tree-link--from-${from}`;
        if (to === 'employee') cls += ' jp-org-tree-link--to-employee';
        return cls;
    }

    function isPositionToEmployeeLink(d) {
        return linkSourceLevel(d) === 'position' && (d.target.data.level || '') === 'employee';
    }

    /** Đường cong Vị trí → Nhân viên (Bezier ngang–dọc mượt). */
    function positionToEmployeePath(sx, sy, tx, ty) {
        const dx = tx - sx;
        if (dx <= 3) {
            return `M${sx},${sy}L${tx},${ty}`;
        }
        const tension = Math.min(0.54, Math.max(0.34, 0.38 + (dx - 72) / (dx * 5)));
        const cx = sx + dx * tension;
        return `M${sx},${sy} C${cx},${sy} ${cx},${ty} ${tx},${ty}`;
    }

    /** Đường vuông góc bo góc — tránh path lỗi khi khoảng cách ngắn. */
    function roundedLinkPath(d, nodeW, urls) {
        const sx = d.source.y + nodeTotalWidth(d.source.data, nodeW, urls);
        const sy = d.source.x;
        const tx = d.target.y + targetAnchorX(d.target.data, nodeW);
        const ty = d.target.x;
        const dx = tx - sx;
        const dy = ty - sy;

        if (isPositionToEmployeeLink(d)) {
            return positionToEmployeePath(sx, sy, tx, ty);
        }

        const minGap = LINK.minGap;
        const stubMin = LINK.stubMin;
        const stubEnd = LINK.stubEnd;

        if (dx <= 4) {
            return `M${sx},${sy}L${tx},${ty}`;
        }
        if (Math.abs(dy) < 1) {
            return `M${sx},${sy}H${tx}`;
        }

        let mx = sx + Math.min(Math.max(dx * 0.45, stubMin), dx - stubEnd);
        mx = Math.max(sx + stubEnd, Math.min(tx - stubEnd, mx));

        const r = Math.min(
            LINK.radius,
            (mx - sx) / 2,
            (tx - mx) / 2,
            Math.abs(dy) / 2,
        );

        if (r < 2 || dx < minGap) {
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
        if (isExpandableLevel(node.level) && node.position_key) {
            keys.add(node.position_key);
        }
        (node.children || []).forEach((c) => collectPositionKeys(c, keys));
    }

    function cloneWithCollapse(tree, collapsed) {
        const copy = JSON.parse(JSON.stringify(tree));
        const showAll = chartState.showAllEmployees;
        function walk(n) {
            if (isExpandableLevel(n.level) && collapsed.has(n.position_key)) {
                n.children = [];
            } else {
                if (showAll && isExpandableLevel(n.level) && Array.isArray(n.employees_all) && n.employees_all.length) {
                    n.children = n.employees_all;
                }
                (n.children || []).forEach(walk);
            }
        }
        walk(copy);
        return copy;
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
        return null;
    }

    function buildActions(nodeData, urls) {
        const level = nodeData.level;
        const id = nodeData.id;
        const deptId = nodeData.dept_id;
        const divId = nodeData.division_id;
        const out = [];

        if (level === 'root') {
            if (!nodeData.has_head && urls.directorAssign) {
                out.push({
                    href: urls.directorAssign,
                    title: 'Gán giám đốc',
                    glyph: HEAD_ASSIGN_GLYPH,
                });
            } else if (nodeData.head_user_id && urls.userEdit) {
                out.push({
                    href: urls.userEdit.replace('{id}', String(nodeData.head_user_id)),
                    title: 'Sửa giám đốc',
                    glyph: '✎',
                });
            } else if (nodeData.has_head && urls.directorAssign) {
                out.push({
                    href: urls.directorAssign,
                    title: 'Thêm giám đốc',
                    glyph: HEAD_ASSIGN_GLYPH,
                });
            }
        }

        if (level === 'department' && id) {
            if (!nodeData.has_head && urls.deptHeadAssign) {
                out.push({
                    href: urls.deptHeadAssign.replace('{dept_id}', String(id)),
                    title: 'Gán trưởng phòng',
                    glyph: HEAD_ASSIGN_GLYPH,
                });
            } else if (nodeData.head_user_id && urls.userEdit) {
                out.push({
                    href: urls.userEdit.replace('{id}', String(nodeData.head_user_id)),
                    title: 'Sửa trưởng phòng',
                    glyph: '✎',
                });
            }
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
            if (!nodeData.has_head && urls.divHeadAssign) {
                out.push({
                    href: fillUrl(urls.divHeadAssign, { dept_id: deptId || '', div_id: id }),
                    title: 'Gán trưởng bộ phận',
                    glyph: HEAD_ASSIGN_GLYPH,
                });
            } else if (nodeData.head_user_id && urls.userEdit) {
                out.push({
                    href: urls.userEdit.replace('{id}', String(nodeData.head_user_id)),
                    title: 'Sửa trưởng bộ phận',
                    glyph: '✎',
                });
            } else if (nodeData.has_head && urls.divHeadAssign) {
                out.push({
                    href: fillUrl(urls.divHeadAssign, { dept_id: deptId || '', div_id: id }),
                    title: 'Thêm trưởng bộ phận',
                    glyph: HEAD_ASSIGN_GLYPH,
                });
            }
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
            const empTotal = Number(nodeData.employee_total ?? nodeData.count ?? 0);
            if (empTotal > 0) {
                out.push({
                    action: 'employeesFull',
                    title: 'Danh sách đầy đủ nhân viên',
                    glyph: '≡',
                });
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

    function isOrgTreeInteractiveTarget(target) {
        if (!target || !target.closest) return false;
        return !!target.closest(
            '.jp-org-tree-node, .jp-org-tree-pill-hit, .jp-org-tree-action-link',
        );
    }

    /** Con lăn trên vùng sơ đồ chỉ zoom — không cuộn thanh trượt / trang. */
    function wireOrgChartViewportWheel(vp) {
        if (!vp || vp.dataset.jpOrgWheelBound === '1') return;
        vp.dataset.jpOrgWheelBound = '1';
        vp.addEventListener(
            'wheel',
            (event) => {
                if (!vp.contains(event.target)) return;
                event.preventDefault();
                const svgEl = vp.querySelector('svg.jp-org-tree-svg');
                if (!svgEl || svgEl.contains(event.target)) return;
                svgEl.dispatchEvent(new WheelEvent('wheel', {
                    bubbles: true,
                    cancelable: true,
                    clientX: event.clientX,
                    clientY: event.clientY,
                    deltaY: event.deltaY,
                    deltaX: event.deltaX,
                    deltaMode: event.deltaMode,
                    ctrlKey: event.ctrlKey,
                    metaKey: event.metaKey,
                }));
            },
            { passive: false, capture: true },
        );
    }

    function showEmployeesListModal(nodeData) {
        const modalEl = document.getElementById('orgEmployeesModal');
        const titleEl = document.getElementById('orgEmployeesModalTitle');
        const subEl = document.getElementById('orgEmployeesModalSubtitle');
        const listEl = document.getElementById('orgEmployeesModalList');
        if (!modalEl || !listEl || !window.bootstrap) return;

        const employees = nodeData.employees_all || [];
        const total = Number(nodeData.employee_total ?? employees.length);
        const posName = (nodeData.name || '').trim() || 'Vị trí';
        if (titleEl) titleEl.textContent = posName;
        if (subEl) {
            subEl.textContent = total
                ? `${total} nhân viên — bấm tên để xem avatar`
                : 'Chưa có nhân viên tại vị trí này.';
        }

        listEl.innerHTML = '';
        if (!employees.length) {
            listEl.innerHTML = '<li class="list-group-item text-muted small">Chưa có nhân viên.</li>';
        } else {
            const urls = chartState.urls || {};
            employees.forEach((emp) => {
                const li = document.createElement('li');
                li.className = 'list-group-item d-flex align-items-center gap-3 jp-org-emp-list-item';
                const name = (emp.name || '').trim() || 'Nhân viên';
                const code = (emp.subtitle || emp.employee_code || '').trim();
                const editUrl = urls.userEdit && emp.user_id
                    ? urls.userEdit.replace('{id}', String(emp.user_id))
                    : '';

                if (emp.avatar_url) {
                    const img = document.createElement('img');
                    img.src = emp.avatar_url;
                    img.alt = '';
                    img.className = 'jp-org-emp-list-avatar rounded-circle';
                    img.loading = 'lazy';
                    li.appendChild(img);
                } else {
                    const av = document.createElement('span');
                    av.className = 'jp-org-emp-list-avatar jp-org-emp-list-avatar--empty';
                    av.setAttribute('aria-hidden', 'true');
                    av.textContent = name.charAt(0).toUpperCase();
                    li.appendChild(av);
                }

                const body = document.createElement('div');
                body.className = 'flex-grow-1 min-width-0';
                const nameBtn = document.createElement('button');
                nameBtn.type = 'button';
                nameBtn.className = 'btn btn-link p-0 text-start fw-bold text-dark text-decoration-none jp-org-emp-list-name';
                nameBtn.textContent = name;
                nameBtn.addEventListener('click', () => showEmployeeAvatar(emp));
                body.appendChild(nameBtn);
                if (code) {
                    const codeEl = document.createElement('div');
                    codeEl.className = 'small text-muted';
                    codeEl.textContent = code;
                    body.appendChild(codeEl);
                }
                if (emp.is_concurrent) {
                    const concEl = document.createElement('div');
                    concEl.className = 'small text-hm';
                    const primary = (emp.primary_dept || '').trim();
                    concEl.textContent = primary
                        ? `Kiêm nhiệm · chính: ${primary}`
                        : 'Kiêm nhiệm';
                    body.appendChild(concEl);
                }
                li.appendChild(body);

                if (editUrl) {
                    const editA = document.createElement('a');
                    editA.href = editUrl;
                    editA.className = 'btn btn-sm btn-outline-hm fw-bold flex-shrink-0';
                    editA.textContent = 'Sửa';
                    li.appendChild(editA);
                }
                listEl.appendChild(li);
            });
        }
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    /** CSS nhúng vào SVG export — tránh var() và stylesheet ngoài (canvas không đọc được). */
    const ORG_EXPORT_STYLES = `
.jp-org-tree-link { fill: none; stroke-linecap: round; stroke-linejoin: round; stroke-width: 2; }
.jp-org-tree-link--from-root { stroke: #991b1b; }
.jp-org-tree-link--from-department { stroke: #dc2626; }
.jp-org-tree-link--from-division { stroke: #f87171; }
.jp-org-tree-link--from-position { stroke: #94a3b8; }
.jp-org-tree-link--from-position.jp-org-tree-link--to-employee { stroke: #64748b; stroke-width: 1.75; }
.jp-org-tree-link--from-unassigned { stroke: #f59e0b; }
.jp-org-tree-link-arrow-fill { fill: #64748b; }
.jp-org-tree-pill-rect { fill: #fff; stroke: #fecaca; stroke-width: 1.5; }
.jp-org-tree-pill-label { font-family: 'Gotham Ultra', Gotham, system-ui, sans-serif; font-size: 13px; font-weight: 400; fill: #1e293b; }
.jp-org-tree-pill-sub { font-family: Gotham, system-ui, sans-serif; font-size: 10px; font-weight: 400; fill: #64748b; }
.jp-org-tree-pill-badge-bg { fill: #fff; stroke: #fca5a5; stroke-width: 1; }
.jp-org-tree-pill-badge-txt { font-family: 'Gotham Ultra', Gotham, system-ui, sans-serif; font-size: 10px; font-weight: 400; fill: #dc2626; }
.jp-org-tree-node--root .jp-org-tree-pill-rect { fill: #dc2626; stroke: #b91c1c; stroke-width: 2; }
.jp-org-tree-node--root .jp-org-tree-pill-label, .jp-org-tree-node--root .jp-org-tree-pill-sub { fill: #fff; }
.jp-org-tree-node--department .jp-org-tree-pill-rect { fill: #fff1f2; stroke: #dc2626; }
.jp-org-tree-node--department .jp-org-tree-pill-sub { fill: #9f1239; }
.jp-org-tree-node--division .jp-org-tree-pill-rect { fill: #fff; stroke: #f9a8d4; }
.jp-org-tree-node--division .jp-org-tree-pill-sub { fill: #831843; }
.jp-org-tree-node--position .jp-org-tree-pill-rect { fill: #f8fafc; stroke: #94a3b8; }
.jp-org-tree-node--position .jp-org-tree-pill-label { font-size: 12px; }
.jp-org-tree-node--employee .jp-org-tree-pill-rect { fill: #f8fafc; stroke: #e2e8f0; }
.jp-org-tree-node--employee .jp-org-tree-pill-label { font-size: 11px; font-weight: 400; fill: #334155; }
.jp-org-tree-node--employee .jp-org-tree-pill-sub { font-size: 9px; fill: #64748b; }
.jp-org-tree-pill-concurrent-bg { fill: #eff6ff; stroke: #93c5fd; stroke-width: 1; }
.jp-org-tree-pill-concurrent-txt { font-family: 'Gotham Ultra', Gotham, system-ui, sans-serif; font-size: 8px; font-weight: 400; fill: #1d4ed8; }
.jp-org-tree-expand-icon { font-family: 'Gotham Ultra', Gotham, system-ui, sans-serif; font-size: 11px; font-weight: 400; fill: #64748b; }
.jp-org-tree-action-bg { fill: #fff; stroke: #cbd5e1; stroke-width: 1.2; }
.jp-org-tree-action-icon { font-family: 'Gotham Ultra', Gotham, system-ui, sans-serif; font-size: 11px; font-weight: 400; fill: #b91c1c; }
.jp-org-tree-action-link.is-danger .jp-org-tree-action-icon { fill: #dc2626; }
`;

    function serializeSvgElement(svgEl) {
        return `<?xml version="1.0" encoding="UTF-8"?>\n${new XMLSerializer().serializeToString(svgEl)}`;
    }

    function downloadSvgFile(svgEl, filename) {
        const xml = serializeSvgElement(svgEl);
        const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.download = filename;
        a.href = url;
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
    }

    function downloadSvgAsPng(svgEl, filename) {
        const xml = serializeSvgElement(svgEl);
        const w = Math.max(1, parseInt(svgEl.getAttribute('width'), 10) || 800);
        const h = Math.max(1, parseInt(svgEl.getAttribute('height'), 10) || 600);

        return new Promise((resolve, reject) => {
            const blob = new Blob([xml], { type: 'image/svg+xml;charset=utf-8' });
            const url = URL.createObjectURL(blob);
            const img = new Image();
            const timeout = window.setTimeout(() => {
                URL.revokeObjectURL(url);
                reject(new Error('timeout'));
            }, 15000);

            img.onload = function onLoad() {
                window.clearTimeout(timeout);
                URL.revokeObjectURL(url);
                try {
                    const scale = 2;
                    const canvas = document.createElement('canvas');
                    canvas.width = w * scale;
                    canvas.height = h * scale;
                    const ctx = canvas.getContext('2d');
                    if (!ctx) {
                        reject(new Error('no-canvas'));
                        return;
                    }
                    ctx.scale(scale, scale);
                    ctx.fillStyle = '#ffffff';
                    ctx.fillRect(0, 0, w, h);
                    ctx.drawImage(img, 0, 0, w, h);
                    canvas.toBlob((pngBlob) => {
                        if (!pngBlob) {
                            reject(new Error('no-blob'));
                            return;
                        }
                        const a = document.createElement('a');
                        a.download = filename;
                        a.href = URL.createObjectURL(pngBlob);
                        a.click();
                        setTimeout(() => URL.revokeObjectURL(a.href), 2000);
                        resolve();
                    }, 'image/png');
                } catch (err) {
                    reject(err);
                }
            };

            img.onerror = function onErr() {
                window.clearTimeout(timeout);
                URL.revokeObjectURL(url);
                reject(new Error('img-error'));
            };

            img.src = url;
        });
    }

    /** Bbox nội dung thật (node + link), không gồm cột guide / transform layout. */
    function getTightChartBBox(chart) {
        const parts = chart.querySelectorAll('.jp-org-tree-nodes, .jp-org-tree-links');
        if (!parts.length) {
            return chart.getBBox();
        }
        let minX = Infinity;
        let minY = Infinity;
        let maxX = -Infinity;
        let maxY = -Infinity;
        parts.forEach((el) => {
            const b = el.getBBox();
            if (!b.width && !b.height) return;
            minX = Math.min(minX, b.x);
            minY = Math.min(minY, b.y);
            maxX = Math.max(maxX, b.x + b.width);
            maxY = Math.max(maxY, b.y + b.height);
        });
        if (!Number.isFinite(minX)) {
            return chart.getBBox();
        }
        return {
            x: minX,
            y: minY,
            width: Math.max(1, maxX - minX),
            height: Math.max(1, maxY - minY),
        };
    }

    function buildExportSvg(chart, defs) {
        const bbox = getTightChartBBox(chart);
        const pad = 28;
        let bx = bbox.x;
        let by = bbox.y;
        let bw = bbox.width;
        let bh = bbox.height;
        if (!bw || !bh || bw < 1 || bh < 1) {
            bx = 0;
            by = 0;
            bw = 1200;
            bh = 800;
        }
        const w = Math.ceil(bw + pad * 2);
        const h = Math.ceil(bh + pad * 2);
        const ns = 'http://www.w3.org/2000/svg';
        const exportSvg = document.createElementNS(ns, 'svg');
        exportSvg.setAttribute('xmlns', ns);
        exportSvg.setAttribute('xmlns:xlink', 'http://www.w3.org/1999/xlink');
        exportSvg.setAttribute('width', String(w));
        exportSvg.setAttribute('height', String(h));
        exportSvg.setAttribute('viewBox', `0 0 ${w} ${h}`);

        const styleEl = document.createElementNS(ns, 'style');
        styleEl.setAttribute('type', 'text/css');
        styleEl.textContent = ORG_EXPORT_STYLES;
        exportSvg.appendChild(styleEl);

        if (defs) {
            exportSvg.appendChild(defs.cloneNode(true));
        }

        const bg = document.createElementNS(ns, 'rect');
        bg.setAttribute('x', '0');
        bg.setAttribute('y', '0');
        bg.setAttribute('width', String(w));
        bg.setAttribute('height', String(h));
        bg.setAttribute('fill', '#ffffff');
        exportSvg.appendChild(bg);

        const chartClone = chart.cloneNode(true);
        chartClone.setAttribute('transform', `translate(${pad - bx},${pad - by})`);
        exportSvg.appendChild(chartClone);
        return exportSvg;
    }

    async function exportOrgChartImage() {
        const mount = document.getElementById('jp-org-tree-mount');
        const svg = mount && mount.querySelector('svg.jp-org-tree-svg');
        const chart = svg && svg.querySelector('g.jp-org-tree-chart');
        const defs = svg && svg.querySelector('defs');
        if (!chart) {
            window.alert('Chưa có sơ đồ để xuất ảnh.');
            return;
        }

        const stamp = new Date();
        const base = `so-do-to-chuc-${stamp.getFullYear()}${String(stamp.getMonth() + 1).padStart(2, '0')}${String(stamp.getDate()).padStart(2, '0')}`;
        const exportSvg = buildExportSvg(chart, defs);

        try {
            await downloadSvgAsPng(exportSvg, `${base}.png`);
        } catch (err) {
            console.error('Export PNG failed', err);
            downloadSvgFile(exportSvg, `${base}.svg`);
            window.alert(
                'Không tạo được file PNG trên trình duyệt này. Đã tải file SVG — mở bằng trình duyệt hoặc chuyển sang PNG.',
            );
        }
    }

    function showEmployeeAvatar(nodeData) {
        const modalEl = document.getElementById('jpAvatarZoomModal');
        const imgEl = document.getElementById('jpAvatarZoomImg');
        const titleEl = document.getElementById('jpAvatarZoomTitle');
        if (!modalEl || !imgEl || !window.bootstrap) return;

        const name = (nodeData.name || '').trim() || 'Nhân viên';
        const url = (nodeData.avatar_url || '').trim();
        const body = imgEl.parentElement;
        let emptyHint = body && body.querySelector('.jp-org-avatar-zoom-empty');
        if (body && !emptyHint) {
            emptyHint = document.createElement('p');
            emptyHint.className = 'jp-org-avatar-zoom-empty text-muted mb-0';
            body.appendChild(emptyHint);
        }
        if (titleEl) titleEl.textContent = name;
        if (url) {
            imgEl.src = url;
            imgEl.alt = name;
            imgEl.classList.remove('d-none');
            if (emptyHint) emptyHint.classList.add('d-none');
        } else {
            imgEl.removeAttribute('src');
            imgEl.alt = '';
            imgEl.classList.add('d-none');
            if (emptyHint) {
                emptyHint.textContent = 'Chưa có ảnh đại diện';
                emptyHint.classList.remove('d-none');
            }
        }
        bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    function syncHeaderColumns(trackEl, columns, marginLeft, transform) {
        if (!trackEl || !columns || !columns.length) return;
        trackEl.style.transform = 'none';
        const headerFs = Math.max(10, Math.round(11 * Math.min(1.15, Math.max(0.95, transform.k))));
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

    function allPositionKeys() {
        const keys = new Set();
        if (chartState.fullData) {
            collectPositionKeys(chartState.fullData, keys);
        }
        return keys;
    }

    function isShowingAllEmployees() {
        if (!chartState.showAllEmployees) return false;
        const keys = allPositionKeys();
        if (!keys.size) return false;
        for (const key of keys) {
            if (chartState.collapsed.has(key)) return false;
        }
        return true;
    }

    function updateShowAllEmployeesButton() {
        const btn = document.getElementById('org-show-all-employees-btn');
        const label = document.getElementById('org-show-all-employees-label');
        const icon = document.getElementById('org-show-all-employees-icon');
        if (!btn || !label) return;
        const showingAll = isShowingAllEmployees();
        label.textContent = showingAll ? ' Ẩn tất cả NV' : ' Hiển thị tất cả NV';
        btn.title = showingAll
            ? 'Ẩn nhân viên ở mọi vị trí trên sơ đồ'
            : 'Hiển thị nhân viên ở mọi vị trí trên sơ đồ';
        btn.setAttribute('aria-pressed', showingAll ? 'true' : 'false');
        if (icon) {
            icon.className = showingAll ? 'bi bi-eye-slash-fill' : 'bi bi-people-fill';
        }
    }

    function toggleShowAllEmployees() {
        const keys = allPositionKeys();
        if (isShowingAllEmployees()) {
            keys.forEach((key) => chartState.collapsed.add(key));
            chartState.showAllEmployees = false;
        } else {
            keys.forEach((key) => chartState.collapsed.delete(key));
            chartState.showAllEmployees = true;
        }
        window.jpOrgTreeInit();
    }

    function togglePosition(key) {
        if (chartState.collapsed.has(key)) {
            chartState.collapsed.delete(key);
        } else {
            chartState.collapsed.add(key);
        }
        if (chartState.showAllEmployees) {
            const keys = allPositionKeys();
            for (const k of keys) {
                if (chartState.collapsed.has(k)) {
                    chartState.showAllEmployees = false;
                    break;
                }
            }
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
        nudgeEmployeeColumn(nodes, nodeW);
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

        const posEmpMarker = defs.append('marker')
            .attr('id', 'jp-org-arrow-pos-emp')
            .attr('viewBox', '0 0 10 10')
            .attr('refX', 9)
            .attr('refY', 5)
            .attr('markerWidth', 7)
            .attr('markerHeight', 7)
            .attr('orient', 'auto');
        posEmpMarker.append('path')
            .attr('d', 'M 1 1 L 9 5 L 1 9 Z')
            .attr('class', 'jp-org-tree-link-arrow-fill');

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
            .attr('marker-end', (d) => (
                isPositionToEmployeeLink(d) ? 'url(#jp-org-arrow-pos-emp)' : null
            ))
            .attr('d', linkPath);

        const nodeG = g.append('g')
            .attr('class', 'jp-org-tree-nodes')
            .selectAll('g')
            .data(nodes)
            .join('g')
            .attr('class', (d) => {
                const lvl = d.data.level || 'item';
                const expanded = isExpandableLevel(lvl)
                    && !chartState.collapsed.has(positionKey(d.data));
                let cls = `jp-org-tree-node jp-org-tree-node--${lvl}`;
                if (primaryHref(d.data, urls)) cls += ' is-clickable';
                if (isExpandableLevel(lvl)) cls += expanded ? ' is-expanded' : ' is-collapsed';
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
            const isExpandable = isExpandableLevel(level);
            const pKey = isExpandable ? positionKey(d.data) : '';
            const expanded = isExpandable && !chartState.collapsed.has(pKey);

            const pill = sel.append('g').attr('class', 'jp-org-tree-pill');

            const pillStroke = level === 'root' ? 2 : isExpandable && expanded ? 2 : 1.5;
            const chevW = isExpandable ? 18 : 0;
            const actW = actionStripWidth(actions);
            const concurrentBadgeW = level === 'employee' && d.data.is_concurrent ? 34 : 0;
            const badgeW = level !== 'employee' ? 30 : concurrentBadgeW;
            const innerPillW = pillW + actW;
            const pillX = chevW;
            const labelX = chevW + 12;
            const badgeX = innerPillW - actW - badgeW - 8;
            const labelMaxW = Math.max(24, badgeX - labelX - 6);

            if (isExpandable) {
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

            pill.select('.jp-org-tree-pill-rect').style('pointer-events', 'none');
            pill.selectAll('text').style('pointer-events', 'none');

            const hit = pill.append('rect')
                .attr('class', 'jp-org-tree-pill-hit')
                .attr('x', 0)
                .attr('y', -pillH / 2)
                .attr('width', innerPillW)
                .attr('height', pillH)
                .attr('fill', 'transparent')
                .attr('rx', PILL_RX)
                .attr('ry', PILL_RX)
                .style('cursor', 'pointer');

            if (isExpandable) {
                hit.on('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    togglePosition(pKey);
                });
            } else if (level === 'employee') {
                hit.on('click', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    showEmployeeAvatar(d.data);
                }).on('dblclick', (ev) => {
                    ev.preventDefault();
                    ev.stopPropagation();
                    const editUrl = urls.userEdit && d.data.user_id
                        ? urls.userEdit.replace('{id}', String(d.data.user_id))
                        : null;
                    if (editUrl) window.location.href = editUrl;
                });
            } else if (href) {
                hit.on('click', (ev) => {
                    if (ev.defaultPrevented) return;
                    ev.stopPropagation();
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
            } else if (d.data.is_concurrent) {
                const badgeH = 18;
                pill.append('rect')
                    .attr('class', 'jp-org-tree-pill-concurrent-bg')
                    .attr('x', badgeX)
                    .attr('y', -badgeH / 2)
                    .attr('width', badgeW)
                    .attr('height', badgeH)
                    .attr('rx', 4)
                    .attr('ry', 4);
                pill.append('text')
                    .attr('class', 'jp-org-tree-pill-concurrent-txt')
                    .attr('x', badgeX + badgeW / 2)
                    .attr('y', 4)
                    .attr('text-anchor', 'middle')
                    .text('Kiêm');
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
                    const cls = `jp-org-tree-action-link${act.danger ? ' is-danger' : ''}`;
                    const drawBtn = (sel) => {
                        sel.append('rect')
                            .attr('class', 'jp-org-tree-action-bg')
                            .attr('width', ACTION.size)
                            .attr('height', ACTION.size)
                            .attr('rx', 5);
                        sel.append('text')
                            .attr('class', 'jp-org-tree-action-icon')
                            .attr('x', ACTION.size / 2)
                            .attr('y', ACTION.size - 6)
                            .attr('text-anchor', 'middle')
                            .text(act.glyph);
                    };
                    if (act.action === 'employeesFull') {
                        const btn = ag.append('g')
                            .attr('class', cls)
                            .attr('role', 'button')
                            .attr('title', act.title)
                            .attr('aria-label', act.title)
                            .style('cursor', 'pointer')
                            .on('click', (ev) => {
                                ev.preventDefault();
                                ev.stopPropagation();
                                showEmployeesListModal(d.data);
                            });
                        drawBtn(btn);
                    } else {
                        const link = ag.append('a')
                            .attr('href', act.href || '#')
                            .attr('class', cls)
                            .attr('title', act.title)
                            .attr('aria-label', act.title)
                            .on('click', (ev) => ev.stopPropagation());
                        drawBtn(link);
                    }
                });
            }

            const hint = level === 'employee'
                ? `${d.data.name}${d.data.subtitle ? ` (${d.data.subtitle})` : ''}`
                : `${d.data.name} — ${d.data.count ?? 0} NV`;
            if (level === 'employee') {
                let tip = hint;
                if (d.data.is_concurrent) {
                    tip += ' — kiêm nhiệm';
                    if (d.data.primary_dept) {
                        tip += ` (vị trí chính: ${d.data.primary_dept})`;
                    }
                }
                pill.append('title').text(
                    `${tip} — bấm xem avatar, double-click sửa hồ sơ`,
                );
            } else if (isExpandable) {
                const total = Number(d.data.employee_total ?? 0);
                const extra = total > EMPLOYEE_PREVIEW_MAX
                    ? ` (tối đa ${EMPLOYEE_PREVIEW_MAX}/${total} trên sơ đồ)`
                    : '';
                pill.append('title').text(
                    `${hint} — bấm để ${expanded ? 'đóng' : 'mở'} xem NV${extra}. Nút ≡ = danh sách đầy đủ`,
                );
            } else {
                pill.append('title').text(hint);
            }
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
                if (isOrgTreeInteractiveTarget(event.target)) return false;
                return true;
            })
            .on('zoom', (event) => scheduleZoomApply(headerTrack, zoomRoot, event.transform));

        svg.call(zoom).on('dblclick.zoom', null);
        wireOrgChartViewportWheel(vp);

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
        updateShowAllEmployeesButton();
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

    function wireOrgToolbar() {
        const showAllBtn = document.getElementById('org-show-all-employees-btn');
        if (showAllBtn) {
            showAllBtn.addEventListener('click', () => {
                toggleShowAllEmployees();
            });
        }
        const exportBtn = document.getElementById('org-export-chart-btn');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => {
                exportBtn.disabled = true;
                Promise.resolve(exportOrgChartImage()).finally(() => {
                    exportBtn.disabled = false;
                });
            });
        }
        updateShowAllEmployeesButton();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            boot();
            wireOrgToolbar();
        });
    } else {
        boot();
        wireOrgToolbar();
    }

    window.jpOrgExportChartImage = exportOrgChartImage;
})();
