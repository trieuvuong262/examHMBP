(function () {
    'use strict';

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () {
        initHourlyModal();
        initProductWizard();
        initReviewGrid();
        autoOpenModals();
    });

    function initHourlyModal() {
        var modal = document.getElementById('hourlyModal');
        if (!modal) return;

        modal.addEventListener('show.bs.modal', function (event) {
            var btn = event.relatedTarget;
            var slotIndex = btn && btn.getAttribute('data-slot-index');
            var slotLabel = btn && btn.getAttribute('data-slot-label');
            var idxInput = document.getElementById('hourly-slot-index');
            var title = document.getElementById('hourly-modal-title');
            var slotText = document.getElementById('hourly-modal-slot');
            if (idxInput) idxInput.value = slotIndex || '';
            if (title) title.textContent = 'Nhập sản lượng';
            if (slotText) slotText.textContent = slotLabel ? 'Khung giờ: ' + slotLabel : '';
            var qty = modal.querySelector('input[name="quantity"]');
            if (qty) { qty.value = ''; qty.focus(); }
        });

        var partialToggle = document.getElementById('hourly-partial-toggle');
        var partialWrap = document.getElementById('hourly-partial-wrap');
        if (partialToggle && partialWrap) {
            partialToggle.addEventListener('change', function () {
                partialWrap.classList.toggle('d-none', !partialToggle.checked);
            });
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

        showStep(1);
    }

    function autoOpenModals() {
        var hourlyModal = document.getElementById('hourlyModal');
        var productModal = document.getElementById('productWizardModal');
        if (typeof bootstrap === 'undefined') return;

        if (productModal && productModal.getAttribute('data-show') === '1') {
            bootstrap.Modal.getOrCreateInstance(productModal).show();
        } else if (hourlyModal) {
            var openBtn = document.querySelector('[data-bs-target="#hourlyModal"]');
            if (openBtn) {
                bootstrap.Modal.getOrCreateInstance(hourlyModal).show();
                var idx = openBtn.getAttribute('data-slot-index');
                var label = openBtn.getAttribute('data-slot-label');
                var idxInput = document.getElementById('hourly-slot-index');
                var slotText = document.getElementById('hourly-modal-slot');
                if (idxInput) idxInput.value = idx || '';
                if (slotText) slotText.textContent = label ? 'Khung giờ: ' + label : '';
            }
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
            root.innerHTML = '<p class="text-muted">Chưa có dữ liệu để tổng kết.</p>';
            return;
        }

        var html = '<div class="table-responsive jp-prod-hourly-scroll"><table class="table table-bordered table-sm jp-prod-hourly-table"><thead><tr class="table-light">';
        html += '<th>STT</th><th>Mã hàng</th><th>Công đoạn</th>';
        grid.slots.forEach(function (s) {
            html += '<th class="jp-ph-slot">' + escapeHtml(s.label) + '</th>';
        });
        html += '</tr></thead><tbody>';

        grid.rows.forEach(function (row, ri) {
            html += '<tr data-product-id="' + row.id + '">';
            html += '<td>' + (ri + 1) + '</td>';
            html += '<td>' + escapeHtml(row.product_code) + '</td>';
            html += '<td>' + escapeHtml(row.process_name) + '</td>';
            row.slots.forEach(function (cell) {
                html += '<td><input type="number" class="jp-review-cell-input" min="0" step="1" ';
                html += 'data-slot-index="' + cell.slot_index + '" value="' + (cell.quantity || '') + '"></td>';
            });
            html += '</tr>';
        });
        html += '</tbody></table></div>';
        root.innerHTML = html;

        var reviewForm = document.getElementById('review-form');
        if (reviewForm) {
            reviewForm.addEventListener('submit', function () {
                var payload = [];
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
                var hidden = document.getElementById('review-json-input');
                if (hidden) hidden.value = JSON.stringify(payload);
            });
        }
    }

    function escapeHtml(str) {
        return String(str || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }
})();
