(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        mountModalsToBody();
        cleanupModalArtifacts();
        initReviewPageLayout();
        initHourlyModal();
        initProductWizard();
        initReviewGrid();
        autoOpenModals();
    });

    function initReviewPageLayout() {
        if (!document.querySelector('.jp-prod-page--review')) return;
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
        ['hourlyModal', 'productWizardModal'].forEach(function (id) {
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

    function initHourlyModal() {
        var modal = document.getElementById('hourlyModal');
        if (!modal) return;

        modal.addEventListener('show.bs.modal', function (event) {
            var btn = event.relatedTarget;
            var slotIndex = btn && btn.getAttribute('data-slot-index');
            var slotLabel = btn && btn.getAttribute('data-slot-label');
            fillHourlyModal(slotIndex, slotLabel);
        });

        modal.addEventListener('hidden.bs.modal', cleanupModalArtifacts);

        var partialToggle = document.getElementById('hourly-partial-toggle');
        var partialWrap = document.getElementById('hourly-partial-wrap');
        if (partialToggle && partialWrap) {
            partialToggle.addEventListener('change', function () {
                partialWrap.classList.toggle('d-none', !partialToggle.checked);
            });
        }

        var qtyInput = document.getElementById('hourly-quantity');
        var reasonWrap = document.getElementById('hourly-zero-reason-wrap');
        var reasonInput = document.getElementById('hourly-zero-reason');
        if (qtyInput && reasonWrap && reasonInput) {
            qtyInput.addEventListener('input', function () {
                var isZero = qtyInput.value === '0';
                reasonWrap.classList.toggle('d-none', !isZero);
                reasonInput.required = isZero;
                if (!isZero) reasonInput.value = '';
            });
        }

        var hourlyForm = document.getElementById('hourly-form');
        if (hourlyForm) {
            hourlyForm.addEventListener('submit', function (e) {
                if (!qtyInput) return;
                if (qtyInput.value === '0' && !(reasonInput && reasonInput.value.trim())) {
                    e.preventDefault();
                    reasonWrap.classList.remove('d-none');
                    reasonInput.required = true;
                    reasonInput.focus();
                }
            });
        }
    }

    function fillHourlyModal(slotIndex, slotLabel) {
        var idxInput = document.getElementById('hourly-slot-index');
        var slotText = document.getElementById('hourly-modal-slot');
        if (idxInput) idxInput.value = slotIndex || '';
        if (slotText) slotText.textContent = slotLabel ? 'Khung giờ: ' + slotLabel : '';
        var modal = document.getElementById('hourlyModal');
        var qty = document.getElementById('hourly-quantity');
        var reasonWrap = document.getElementById('hourly-zero-reason-wrap');
        var reasonInput = document.getElementById('hourly-zero-reason');
        if (qty) {
            qty.value = '';
            if (reasonWrap) reasonWrap.classList.add('d-none');
            if (reasonInput) {
                reasonInput.value = '';
                reasonInput.required = false;
            }
            setTimeout(function () { qty.focus(); }, 200);
        }
    }

    function initProductWizard() {
        var modal = document.getElementById('productWizardModal');
        if (!modal) return;

        var form = document.getElementById('product-wizard-form');
        var nextBtn = document.getElementById('wizard-next-btn');
        var submitBtn = document.getElementById('wizard-submit-btn');
        var title = document.getElementById('wizard-title');
        var panes = modal.querySelectorAll('.wizard-pane');
        var steps = modal.querySelectorAll('.jp-prod-wizard-steps span');
        var current = 1;

        function showStep(n) {
            current = n;
            panes.forEach(function (pane) {
                var step = parseInt(pane.getAttribute('data-step'), 10);
                pane.classList.toggle('d-none', step !== n);
                var input = pane.querySelector('input');
                if (input) input.required = step === n;
            });
            steps.forEach(function (s) {
                var step = parseInt(s.getAttribute('data-step'), 10);
                s.classList.toggle('active', step === n);
                s.classList.toggle('done', step < n);
            });
            var titles = { 1: 'Mã hàng', 2: 'Tên công đoạn', 3: 'Định mức 1 giờ' };
            if (title) title.textContent = titles[n] || '';
            if (nextBtn) nextBtn.classList.toggle('d-none', n >= 3);
            if (submitBtn) submitBtn.classList.toggle('d-none', n < 3);
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', function () {
                var pane = modal.querySelector('.wizard-pane[data-step="' + current + '"]');
                var input = pane && pane.querySelector('input');
                if (input && !input.value.trim()) {
                    input.focus();
                    input.reportValidity();
                    return;
                }
                showStep(current + 1);
                var nextPane = modal.querySelector('.wizard-pane[data-step="' + (current) + '"] input');
                if (nextPane) nextPane.focus();
            });
        }

        if (form) {
            form.addEventListener('submit', function (e) {
                if (current < 3) {
                    e.preventDefault();
                    showStep(3);
                }
            });
        }

        modal.addEventListener('hidden.bs.modal', cleanupModalArtifacts);
        showStep(1);
    }

    function autoOpenModals() {
        var productModal = document.getElementById('productWizardModal');
        if (!productModal || typeof bootstrap === 'undefined') return;

        if (productModal.getAttribute('data-show') === '1') {
            setTimeout(function () { openModal(productModal); }, 100);
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

        if (rootMobile) {
            rootMobile.innerHTML = renderReviewMobileCards(grid);
            rootMobile.addEventListener('input', onReviewInput);
        }
        if (rootDesktop) {
            rootDesktop.innerHTML = renderReviewDesktopTable(grid);
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
        ];
        forms.forEach(function (form) {
            if (!form || form.dataset.bound === '1') return;
            form.dataset.bound = '1';
            form.addEventListener('submit', function () {
                fillReviewPayload();
            });
        });
    }

    function renderReviewMobileCards(grid) {
        var html = '<div class="jp-prod-review-list">';
        grid.rows.forEach(function (row, ri) {
            html += renderReviewMobileCard(row, ri);
        });
        html += '</div>';
        return html;
    }

    function renderReviewMobileCard(row, ri) {
        var code = escapeHtml(row.label_code || row.product_code || '—');
        var process = escapeHtml(row.label_process || row.process_name || 'Chưa gắn mã');
        var unfinalized = row.is_unfinalized ? ' is-unfinalized' : '';
        var html = '<article class="jp-prod-review-product' + unfinalized + '" data-product-id="' + row.id + '">';
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
        }
        html += '</header><div class="jp-prod-review-slots">';

        var rowTotal = 0;
        row.slots.forEach(function (cell) {
            if (cell.is_na || !cell.has_data) return;
            var qty = parseInt(cell.quantity, 10) || 0;
            if (qty > 0) rowTotal += qty;
            var label = escapeHtml(cell.slot_label || ('Giờ ' + (cell.slot_index + 1)));
            html += '<div class="jp-prod-review-slot">';
            html += '<div class="jp-prod-review-slot-label">' + label + '</div>';
            html += '<input type="number" class="jp-prod-review-qty-input" min="0" step="1" inputmode="numeric" ';
            html += 'data-slot-index="' + cell.slot_index + '" value="' + qty + '" aria-label="Sản lượng ' + label + '">';
            html += '<span class="jp-prod-review-slot-cum">Σ ' + (cell.cumulative || qty) + '</span>';
            html += '</div>';
        });

        html += '</div><footer class="jp-prod-review-row-total">Tổng dòng: <strong class="jp-prod-row-total-val">' + (row.total_quantity || rowTotal) + '</strong></footer>';
        html += '</article>';
        return html;
    }

    function renderReviewDesktopTable(grid) {
        var html = '<div class="jp-prod-hourly-sheet-wrap"><div class="table-responsive jp-prod-hourly-scroll">';
        html += '<table class="table table-bordered table-sm jp-prod-hourly-table mb-0"><thead><tr class="table-light">';
        html += '<th class="jp-ph-stt">STT</th><th class="jp-ph-code">Mã hàng</th><th class="jp-ph-process">Tên công đoạn</th><th class="jp-ph-norm">ĐM 1 giờ</th>';
        grid.slots.forEach(function (slot) {
            html += '<th class="jp-ph-slot">' + escapeHtml(slot.label) + '</th>';
        });
        html += '<th class="text-end">Tổng dòng</th></tr></thead><tbody>';

        grid.rows.forEach(function (row, ri) {
            var rowClass = row.is_unfinalized ? ' class="table-warning"' : '';
            html += '<tr data-product-id="' + row.id + '"' + rowClass + '>';
            html += '<td class="text-center">' + (ri + 1) + '</td>';
            html += '<td class="fw-semibold">' + escapeHtml(row.label_code || row.product_code || '—');
            if (row.is_unfinalized) {
                html += ' <span class="badge bg-warning text-dark ms-1">Chưa gắn</span>';
            }
            html += '</td>';
            html += '<td>' + escapeHtml(row.label_process || row.process_name || 'Chưa gắn mã') + '</td>';
            html += '<td class="text-end">' + escapeHtml(row.norm_per_hour || '—') + '</td>';

            var rowTotal = 0;
            row.slots.forEach(function (cell) {
                html += '<td class="text-center align-middle">';
                if (cell.is_na) {
                    html += '<span class="text-muted">—</span>';
                } else if (cell.has_data) {
                    var qty = parseInt(cell.quantity, 10) || 0;
                    if (qty > 0) rowTotal += qty;
                    html += '<input type="number" class="jp-review-cell-input" min="0" step="1" ';
                    html += 'data-slot-index="' + cell.slot_index + '" value="' + qty + '">';
                }
                html += '</td>';
            });
            html += '<td class="text-end fw-bold jp-prod-row-total-val">' + (row.total_quantity || rowTotal) + '</td>';
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
                    rowTotal += parseInt(inp.value, 10) || 0;
                });
                grand += rowTotal;
                var el = tr.querySelector('.jp-prod-row-total-val');
                if (el) el.textContent = rowTotal;
            });
        } else {
            root.querySelectorAll('.jp-prod-review-product').forEach(function (article) {
                var rowTotal = 0;
                article.querySelectorAll('.jp-prod-review-qty-input').forEach(function (inp) {
                    rowTotal += parseInt(inp.value, 10) || 0;
                });
                grand += rowTotal;
                var el = article.querySelector('.jp-prod-row-total-val');
                if (el) el.textContent = rowTotal;
            });
        }

        ['review-grand-total', 'review-grand-total-desktop'].forEach(function (id) {
            var grandEl = document.getElementById(id);
            if (grandEl) grandEl.textContent = grand;
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
                        quantity: parseInt(inp.value, 10) || 0,
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
                        quantity: parseInt(inp.value, 10) || 0,
                    });
                });
                payload.push({ product_id: parseInt(productId, 10), slots: slots });
            });
        }

        var json = JSON.stringify(payload);
        ['review-json-input', 'review-json-input-desktop'].forEach(function (id) {
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
