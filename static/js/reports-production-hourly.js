(function () {
    'use strict';

    function formatProdQty(value) {
        var n = parseFloat(value);
        if (!isFinite(n) || n === 0) return '0';
        if (Math.floor(n) === n) return String(Math.floor(n));
        return String(n).replace(/\.?0+$/, '');
    }

    function parseProdQty(value) {
        var n = parseFloat(value);
        return isFinite(n) ? n : 0;
    }

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        mountModalsToBody();
        cleanupModalArtifacts();
        initReviewPageLayout();
        initCompleteSessionModal();
        initReviewGrid();
        initSubmitConfirm();
        autoOpenModals();
        focusMobileCompleteQty();
        initServerClock();
    });

    function initReviewPageLayout() {
        if (
            !document.querySelector('.jp-prod-page--review')
            && !document.querySelector('.jp-prod-page--proxy-mode')
        ) return;
        document.body.classList.add('jp-prod-hourly-review');
        syncReviewStickySpacer();
        window.addEventListener('resize', syncReviewStickySpacer);
    }

    function syncReviewStickySpacer() {
        var sticky = document.querySelector('.jp-prod-review-sticky');
        var spacer = document.querySelector('.jp-prod-review-sticky-spacer');
        if (!sticky || !spacer) return;
        spacer.style.height = sticky.offsetHeight + 'px';
    }

    /** Modal trong main content dễ bị backdrop che (màn hình mờ, không bấm được). */
    function mountModalsToBody() {
        ['completeSessionModal'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el && el.parentElement !== document.body) {
                document.body.appendChild(el);
            }
        });
    }

    function cleanupModalArtifacts() {
        document.querySelectorAll('.modal-backdrop').forEach(function (el) { el.remove(); });
        document.body.classList.remove('modal-open');
        document.body.style.removeProperty('overflow');
        document.body.style.removeProperty('padding-right');
        document.querySelectorAll('.modal.show').forEach(function (modal) {
            modal.classList.remove('show');
            modal.style.removeProperty('display');
            modal.setAttribute('aria-hidden', 'true');
        });
    }

    function openModal(el, setupFn) {
        if (!el || typeof bootstrap === 'undefined') return;
        cleanupModalArtifacts();
        if (typeof setupFn === 'function') setupFn();
        var instance = bootstrap.Modal.getOrCreateInstance(el, { backdrop: true, keyboard: true });
        instance.show();
    }

    function initServerClock() {
        var page = document.querySelector('.jp-prod-page[data-server-now]');
        if (!page) return;
        var raw = page.getAttribute('data-server-now');
        if (!raw) return;
        var serverStart = Date.parse(raw);
        if (!isFinite(serverStart)) return;
        var clientStart = Date.now();

        function pad(n) {
            return n < 10 ? '0' + n : String(n);
        }

        function formatServerTime(ms) {
            var d = new Date(ms);
            return pad(d.getHours()) + ':' + pad(d.getMinutes());
        }

        function tick() {
            var nowMs = serverStart + (Date.now() - clientStart);
            var label = formatServerTime(nowMs);
            document.querySelectorAll('[data-server-clock]').forEach(function (el) {
                el.textContent = label;
            });
        }

        tick();
        setInterval(tick, 30000);
    }

    function initCompleteSessionModal() {
        document.querySelectorAll('.jp-prod-complete-form').forEach(function (form) {
            var qtyInput = form.querySelector('.jp-prod-complete-qty');
            var reasonWrap = form.querySelector('.jp-prod-complete-zero-wrap');
            var reasonInput = form.querySelector('.jp-prod-complete-zero-reason');
            var extraWrap = form.querySelector('.jp-prod-complete-extra-wrap');
            var damagedInput = form.querySelector('.jp-prod-complete-damaged');
            if (!qtyInput || !reasonWrap || !reasonInput) return;

            qtyInput.addEventListener('input', function () {
                var isZero = qtyInput.value === '0';
                reasonWrap.classList.toggle('d-none', !isZero);
                reasonInput.required = isZero;
                if (!isZero) reasonInput.value = '';
                if (extraWrap) extraWrap.classList.toggle('d-none', isZero);
                if (isZero && damagedInput) damagedInput.value = '';
            });

            form.addEventListener('submit', function (e) {
                if (qtyInput.value === '0' && !(reasonInput.value || '').trim()) {
                    e.preventDefault();
                    reasonWrap.classList.remove('d-none');
                    reasonInput.required = true;
                    reasonInput.focus();
                }
            });
        });

        var modal = document.getElementById('completeSessionModal');
        if (modal) {
            modal.addEventListener('hidden.bs.modal', cleanupModalArtifacts);
        }
    }

    function focusMobileCompleteQty() {
        if (window.matchMedia('(min-width: 992px)').matches) return;
        var input = document.querySelector('#complete-session-form-mobile .jp-prod-complete-qty');
        if (input) setTimeout(function () { input.focus(); }, 300);
    }

    function autoOpenModals() {
        if (!window.matchMedia('(min-width: 992px)').matches) return;
        var completeModal = document.getElementById('completeSessionModal');
        if (!completeModal || typeof bootstrap === 'undefined') return;

        if (completeModal.getAttribute('data-show') === '1') {
            setTimeout(function () { openModal(completeModal); }, 100);
        }
    }

    function initReviewGrid() {
        var rootMobile = document.getElementById('review-grid-root');
        var rootDesktop = document.getElementById('review-grid-root-desktop');
        var dataEl = document.getElementById('hourly-grid-data');
        if ((!rootMobile && !rootDesktop) || !dataEl) return;

        var grid;
        try {
            grid = JSON.parse(dataEl.textContent);
        } catch (e) {
            return;
        }

        if (!grid.rows || !grid.rows.length) {
            var emptyMsg = '<p class="text-muted text-center py-3">Chưa có dữ liệu để tổng kết.</p>';
            if (rootMobile) rootMobile.innerHTML = emptyMsg;
            if (rootDesktop) rootDesktop.innerHTML = emptyMsg;
            return;
        }

        var proxyMode = !!grid.proxy_mode;

        if (rootMobile) {
            rootMobile.innerHTML = renderReviewMobileCards(grid, proxyMode);
            rootMobile.addEventListener('input', onReviewInput);
        }
        if (rootDesktop) {
            rootDesktop.innerHTML = renderReviewDesktopTable(grid, proxyMode);
            rootDesktop.addEventListener('input', onReviewInput);
        }

        bindReviewSubmitForms();
        syncReviewStickySpacer();
    }

    function onReviewInput(e) {
        if (
            !e.target.classList.contains('jp-prod-review-qty-input')
            && !e.target.classList.contains('jp-review-cell-input')
        ) return;
        recalcReviewTotals();
    }

    function bindReviewSubmitForms() {
        var forms = [
            document.getElementById('review-submit-form'),
            document.getElementById('review-submit-form-desktop'),
            document.getElementById('review-save-form'),
            document.getElementById('review-save-form-desktop'),
        ];
        forms.forEach(function (form) {
            if (!form || form.dataset.bound === '1') return;
            form.dataset.bound = '1';
            form.addEventListener('submit', function () {
                fillReviewPayload();
            });
        });
    }

    function initSubmitConfirm() {
        var modalEl = document.getElementById('prodSubmitConfirmModal');
        if (!modalEl || typeof bootstrap === 'undefined') return;

        var pendingForm = null;
        var modal = bootstrap.Modal.getOrCreateInstance(modalEl);

        document.querySelectorAll('.js-prod-submit-trigger').forEach(function (btn) {
            btn.addEventListener('click', function () {
                pendingForm = btn.closest('form.js-prod-submit-form');
                if (!pendingForm) return;
                fillReviewPayload();
                modal.show();
            });
        });

        var confirmBtn = document.getElementById('prodSubmitConfirmBtn');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function () {
                if (!pendingForm) return;
                fillReviewPayload();
                modal.hide();
                pendingForm.submit();
                pendingForm = null;
            });
        }

        modalEl.addEventListener('hidden.bs.modal', function () {
            pendingForm = null;
        });
    }

    function renderReviewMobileCards(grid, proxyMode) {
        var html = '<div class="jp-prod-review-list">';
        grid.rows.forEach(function (row, ri) {
            html += renderReviewMobileCard(row, ri, proxyMode);
        });
        html += '</div>';
        return html;
    }

    function renderReviewMobileCard(row, ri, proxyMode) {
        var code = escapeHtml(row.label_code || row.product_code || '—');
        var process = escapeHtml(row.label_process || row.process_name || 'Chưa gắn mã');
        var unfinalized = row.is_unfinalized ? ' is-unfinalized' : '';
        var locked = row.submitted_locked ? ' is-submitted-locked' : '';
        var html = '<article class="jp-prod-review-product' + unfinalized + locked + '" data-product-id="' + row.id + '">';
        html += '<header class="jp-prod-review-product-head">';
        html += '<span class="jp-prod-review-num">' + (ri + 1) + '</span>';
        html += '<div class="jp-prod-review-product-meta">';
        html += '<div class="jp-prod-review-code">' + code + '</div>';
        html += '<div class="jp-prod-review-process">' + process + '</div>';
        if (row.norm_per_hour) {
            html += '<div class="jp-prod-review-norm">ĐM ' + escapeHtml(row.norm_per_hour) + '/giờ</div>';
        }
        html += '</div>';
        if (row.is_unfinalized) {
            html += '<span class="badge bg-warning text-dark jp-prod-review-badge">Chưa gắn</span>';
        } else if (row.submitted_locked) {
            html += '<span class="badge bg-secondary-subtle text-secondary jp-prod-review-badge">Đã gửi</span>';
        }
        html += '</header><div class="jp-prod-review-slots">';

        var rowTotal = 0;
        row.slots.forEach(function (cell) {
            if (cell.is_na) return;
            if (!proxyMode && !cell.has_data) return;
            var qty = parseProdQty(cell.quantity);
            if (qty > 0) rowTotal += qty;
            var label = escapeHtml(cell.slot_label || ('Giờ ' + (cell.slot_index + 1)));
            html += '<div class="jp-prod-review-slot">';
            html += '<div class="jp-prod-review-slot-label">' + label + '</div>';
            if (row.submitted_locked) {
                html += '<div class="jp-prod-review-qty-readonly">' + formatProdQty(qty) + '</div>';
            } else {
                html += '<input type="number" class="jp-prod-review-qty-input" min="0" step="0.01" inputmode="decimal" ';
                html += 'data-slot-index="' + cell.slot_index + '" value="' + qty + '" aria-label="Sản lượng ' + label + '">';
            }
            html += '<span class="jp-prod-review-slot-cum">Σ ' + formatProdQty(cell.cumulative || qty) + '</span>';
            html += '</div>';
        });

        html += '</div><footer class="jp-prod-review-row-total">Tổng dòng: <strong class="jp-prod-row-total-val">' + formatProdQty(row.total_quantity || rowTotal) + '</strong></footer>';
        html += '</article>';
        return html;
    }

    function renderReviewDesktopTable(grid, proxyMode) {
        var html = '<div class="jp-prod-hourly-sheet-wrap"><div class="table-responsive jp-prod-hourly-scroll">';
        html += '<table class="table table-bordered table-sm jp-prod-hourly-table mb-0"><thead><tr class="table-light">';
        html += '<th class="jp-ph-stt">STT</th><th class="jp-ph-code">Mã hàng</th><th class="jp-ph-process">Tên công đoạn</th><th class="jp-ph-norm">ĐM 1 giờ</th>';
        grid.slots.forEach(function (slot) {
            var otClass = slot.is_overtime ? ' jp-ph-slot--overtime' : '';
            html += '<th class="jp-ph-slot' + otClass + '">' + escapeHtml(slot.label) + '</th>';
        });
        html += '<th class="text-end">Tổng dòng</th></tr></thead><tbody>';

        grid.rows.forEach(function (row, ri) {
            var rowClass = row.is_unfinalized ? ' class="table-warning"' : (row.submitted_locked ? ' class="table-secondary"' : '');
            html += '<tr data-product-id="' + row.id + '"' + rowClass + '>';
            html += '<td class="text-center">' + (ri + 1) + '</td>';
            html += '<td class="fw-semibold">' + escapeHtml(row.label_code || row.product_code || '—');
            if (row.is_unfinalized) {
                html += ' <span class="badge bg-warning text-dark ms-1">Chưa gắn</span>';
            } else if (row.submitted_locked) {
                html += ' <span class="badge bg-secondary-subtle text-secondary ms-1">Đã gửi</span>';
            }
            html += '</td>';
            html += '<td>' + escapeHtml(row.label_process || row.process_name || 'Chưa gắn mã') + '</td>';
            html += '<td class="text-end">' + escapeHtml(row.norm_per_hour || '—') + '</td>';

            var rowTotal = 0;
            row.slots.forEach(function (cell) {
                html += '<td class="text-center align-middle">';
                if (cell.is_na) {
                    html += '<span class="text-muted">—</span>';
                } else if (cell.has_data || proxyMode) {
                    var qty = parseProdQty(cell.quantity);
                    if (qty > 0) rowTotal += qty;
                    if (row.submitted_locked) {
                        html += '<span class="jp-review-qty-readonly">' + formatProdQty(qty) + '</span>';
                    } else {
                        html += '<input type="number" class="jp-review-cell-input" min="0" step="0.01" ';
                        html += 'data-slot-index="' + cell.slot_index + '" value="' + qty + '">';
                    }
                }
                html += '</td>';
            });
            html += '<td class="text-end fw-bold jp-prod-row-total-val">' + formatProdQty(row.total_quantity || rowTotal) + '</td>';
            html += '</tr>';
        });

        html += '</tbody></table></div></div>';
        return html;
    }

    function getActiveReviewRoot() {
        if (window.matchMedia('(min-width: 768px)').matches) {
            return document.getElementById('review-grid-root-desktop') || document.getElementById('review-grid-root');
        }
        return document.getElementById('review-grid-root') || document.getElementById('review-grid-root-desktop');
    }

    function recalcReviewTotals() {
        var grand = 0;
        var root = getActiveReviewRoot();
        if (!root) return;

        if (root.id === 'review-grid-root-desktop') {
            root.querySelectorAll('tr[data-product-id]').forEach(function (tr) {
                var rowTotal = 0;
                tr.querySelectorAll('.jp-review-cell-input').forEach(function (inp) {
                    rowTotal += parseProdQty(inp.value);
                });
                grand += rowTotal;
                var el = tr.querySelector('.jp-prod-row-total-val');
                if (el) el.textContent = formatProdQty(rowTotal);
            });
        } else {
            root.querySelectorAll('.jp-prod-review-product').forEach(function (article) {
                var rowTotal = 0;
                article.querySelectorAll('.jp-prod-review-qty-input').forEach(function (inp) {
                    rowTotal += parseProdQty(inp.value);
                });
                grand += rowTotal;
                var el = article.querySelector('.jp-prod-row-total-val');
                if (el) el.textContent = formatProdQty(rowTotal);
            });
        }

        ['review-grand-total', 'review-grand-total-desktop', 'review-grand-total-mobile'].forEach(function (id) {
            var grandEl = document.getElementById(id);
            if (grandEl) grandEl.textContent = formatProdQty(grand);
        });
    }

    function fillReviewPayload() {
        var root = getActiveReviewRoot();
        var payload = [];
        if (!root) return;

        if (root.id === 'review-grid-root-desktop') {
            root.querySelectorAll('tr[data-product-id]').forEach(function (tr) {
                var productId = tr.getAttribute('data-product-id');
                var slots = [];
                tr.querySelectorAll('.jp-review-cell-input').forEach(function (inp) {
                    slots.push({
                        slot_index: parseInt(inp.getAttribute('data-slot-index'), 10),
                        quantity: parseProdQty(inp.value),
                    });
                });
                payload.push({ product_id: parseInt(productId, 10), slots: slots });
            });
        } else {
            root.querySelectorAll('.jp-prod-review-product').forEach(function (article) {
                var productId = article.getAttribute('data-product-id');
                var slots = [];
                article.querySelectorAll('.jp-prod-review-qty-input').forEach(function (inp) {
                    slots.push({
                        slot_index: parseInt(inp.getAttribute('data-slot-index'), 10),
                        quantity: parseProdQty(inp.value),
                    });
                });
                payload.push({ product_id: parseInt(productId, 10), slots: slots });
            });
        }

        var json = JSON.stringify(payload);
        [
            'review-json-input',
            'review-json-input-desktop',
            'review-json-save',
            'review-json-save-desktop',
        ].forEach(function (id) {
            var hidden = document.getElementById(id);
            if (hidden) hidden.value = json;
        });
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
})();
