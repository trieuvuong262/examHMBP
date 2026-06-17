(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        mountModalsToBody();
        cleanupModalArtifacts();
        initHourlyModal();
        initProductWizard();
        initReviewGrid();
        autoOpenModals();
    });

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
    }

    function fillHourlyModal(slotIndex, slotLabel) {
        var idxInput = document.getElementById('hourly-slot-index');
        var slotText = document.getElementById('hourly-modal-slot');
        if (idxInput) idxInput.value = slotIndex || '';
        if (slotText) slotText.textContent = slotLabel ? 'Khung giờ: ' + slotLabel : '';
        var modal = document.getElementById('hourlyModal');
        var qty = modal && modal.querySelector('input[name="quantity"]');
        if (qty) {
            qty.value = '';
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
        var root = document.getElementById('review-grid-root');
        var dataEl = document.getElementById('hourly-grid-data');
        if (!root || !dataEl) return;

        var grid;
        try {
            grid = JSON.parse(dataEl.textContent);
        } catch (e) {
            return;
        }

        if (!grid.rows || !grid.rows.length) {
            root.innerHTML = '<p class="text-muted text-center py-3">Chưa có dữ liệu để tổng kết.</p>';
            return;
        }

        var html = '<div class="jp-prod-review-list">';
        grid.rows.forEach(function (row, ri) {
            var code = escapeHtml(row.label_code || row.product_code || '—');
            var process = escapeHtml(row.label_process || row.process_name || 'Chưa gắn mã');
            var unfinalized = row.is_unfinalized ? ' is-unfinalized' : '';
            html += '<article class="jp-prod-review-product' + unfinalized + '" data-product-id="' + row.id + '">';
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
                if (!cell.quantity && cell.quantity !== 0) return;
                if (parseInt(cell.quantity, 10) <= 0) return;
                var qty = parseInt(cell.quantity, 10) || 0;
                rowTotal += qty;
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
        });
        html += '</div>';
        root.innerHTML = html;

        root.addEventListener('input', function (e) {
            if (!e.target.classList.contains('jp-prod-review-qty-input')) return;
            recalcReviewTotals(root);
        });

        var saveBtn = document.getElementById('review-save-btn');
        var reviewForm = document.getElementById('review-form');
        if (saveBtn && reviewForm) {
            saveBtn.addEventListener('click', function () {
                fillReviewPayload(root);
                reviewForm.submit();
            });
        }
    }

    function recalcReviewTotals(root) {
        var grand = 0;
        root.querySelectorAll('.jp-prod-review-product').forEach(function (article) {
            var rowTotal = 0;
            article.querySelectorAll('.jp-prod-review-qty-input').forEach(function (inp) {
                rowTotal += parseInt(inp.value, 10) || 0;
            });
            grand += rowTotal;
            var el = article.querySelector('.jp-prod-row-total-val');
            if (el) el.textContent = rowTotal;
        });
        var grandEl = document.getElementById('review-grand-total');
        if (grandEl) grandEl.textContent = grand;
    }

    function fillReviewPayload(root) {
        var payload = [];
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
        var hidden = document.getElementById('review-json-input');
        if (hidden) hidden.value = JSON.stringify(payload);
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
})();
