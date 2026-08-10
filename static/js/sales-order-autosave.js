/**
 * Auto-save form lên đơn đặt hàng (san-xuat/don-hang/them) vào localStorage.
 * Khi load lại trang, nếu form còn trống thì restore bản nháp (< 7 ngày).
 * Xóa draft khi submit (giống báo cáo VP).
 */
(function () {
    'use strict';

    var form = document.getElementById('jp-so-form');
    if (!form) return;

    var STORAGE_KEY = 'sx_sales_order_draft';
    var SAVE_INTERVAL = 3000;
    var HEADER_FIELDS = ['code', 'customer_name', 'request_date', 'due_date', 'notes'];
    // File đính kèm không lưu localStorage (không serialize được).

    function headerEl(name) {
        return form.querySelector('[name="' + name + '"]');
    }

    function visibleLineRows() {
        var rows = [];
        document.querySelectorAll('#jp-so-lines-table tbody tr.jp-so-line-row').forEach(function (row) {
            if (row.style.display === 'none') return;
            var del = row.querySelector('input[type=checkbox][name$="-DELETE"]');
            if (del && del.checked) return;
            rows.push(row);
        });
        return rows;
    }

    function syncAllSizeJson() {
        visibleLineRows().forEach(function (row) {
            if (typeof window.jpSoSyncLineSizeJson === 'function') {
                window.jpSoSyncLineSizeJson(row);
            }
        });
    }

    function collectLines() {
        syncAllSizeJson();
        var lines = [];
        visibleLineRows().forEach(function (row) {
            var codeEl = row.querySelector('.jp-sx-product-code-select, select[name$="-product_code"]');
            var nameEl = row.querySelector('input[name$="-product_name"]');
            var qtyEl = row.querySelector('.jp-so-qty-total, input[name$="-qty"]');
            var sizeEl = row.querySelector('.jp-so-size-qtys-json, input[name$="-size_qtys"]');
            var code = codeEl ? (codeEl.value || '').trim() : '';
            var name = nameEl ? (nameEl.value || '').trim() : '';
            var qty = qtyEl ? (qtyEl.value || '').trim() : '';
            var sizeRaw = sizeEl ? (sizeEl.value || '').trim() : '';
            var sizeQtys = {};
            if (sizeRaw) {
                try {
                    var parsed = JSON.parse(sizeRaw);
                    if (parsed && typeof parsed === 'object') sizeQtys = parsed;
                } catch (e) { /* ignore */ }
            }
            if (!code && !name && (!qty || qty === '0') && !Object.keys(sizeQtys).length) return;
            lines.push({
                product_code: code,
                product_name: name,
                qty: qty,
                size_qtys: sizeQtys,
            });
        });
        return lines;
    }

    function collectDraft() {
        var header = {};
        HEADER_FIELDS.forEach(function (name) {
            var el = headerEl(name);
            header[name] = el ? el.value : '';
        });
        return {
            header: header,
            lines: collectLines(),
            ts: Date.now(),
        };
    }

    function hasMeaningfulContent(draft) {
        if (!draft) return false;
        var h = draft.header || {};
        if ((h.code || '').trim()) return true;
        if ((h.customer_name || '').trim()) return true;
        if ((h.due_date || '').trim()) return true;
        if ((h.notes || '').trim()) return true;
        var lines = draft.lines || [];
        for (var i = 0; i < lines.length; i++) {
            var line = lines[i] || {};
            if ((line.product_code || '').trim()) return true;
            if ((line.product_name || '').trim()) return true;
            if ((line.qty || '').trim() && line.qty !== '0') return true;
            if (line.size_qtys && typeof line.size_qtys === 'object') {
                var keys = Object.keys(line.size_qtys);
                for (var j = 0; j < keys.length; j++) {
                    if (Number(line.size_qtys[keys[j]]) > 0) return true;
                }
            }
        }
        return false;
    }

    function formIsEmpty() {
        return !hasMeaningfulContent(collectDraft());
    }

    function saveDraft() {
        var draft = collectDraft();
        if (hasMeaningfulContent(draft)) {
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(draft)); } catch (e) {}
        } else {
            try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
        }
    }

    function loadDraft() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            var draft = JSON.parse(raw);
            if (draft.ts && (Date.now() - draft.ts) > 7 * 24 * 60 * 60 * 1000) {
                localStorage.removeItem(STORAGE_KEY);
                return null;
            }
            return draft;
        } catch (e) {
            return null;
        }
    }

    function ensureRowCount(n) {
        var addBtn = document.getElementById('jp-so-add-row');
        if (!addBtn) return;
        while (visibleLineRows().length < n) {
            addBtn.click();
        }
    }

    function setProductCode(row, code, name) {
        code = (code || '').trim();
        name = (name || '').trim();
        var select = row.querySelector('.jp-sx-product-code-select, select[name$="-product_code"]');
        var nameEl = row.querySelector('input[name$="-product_name"]');
        if (nameEl && name) nameEl.value = name;
        if (!select) return;
        if (!code) {
            if (select.tomselect) select.tomselect.clear(true);
            else select.value = '';
            return;
        }
        var label = name ? (code + ' — ' + name) : code;
        if (select.tomselect) {
            var ts = select.tomselect;
            if (!ts.options[code]) {
                ts.addOption({ id: code, code: code, text: label, name: name });
            } else if (name && ts.options[code]) {
                ts.updateOption(code, { id: code, code: code, text: label, name: name });
            }
            ts.setValue(code, true);
        } else {
            var opt = Array.prototype.find.call(select.options || [], function (o) {
                return o.value === code;
            });
            if (!opt) {
                opt = document.createElement('option');
                opt.value = code;
                opt.textContent = label;
                select.appendChild(opt);
            }
            select.value = code;
            if (typeof window.jpInitProductCodeSelect === 'function') {
                window.jpInitProductCodeSelect(select);
            }
        }
        if (nameEl && name) nameEl.value = name;
    }

    function restoreDraft(draft) {
        var h = draft.header || {};
        HEADER_FIELDS.forEach(function (name) {
            var el = headerEl(name);
            if (!el) return;
            if (h[name] != null && h[name] !== '') el.value = h[name];
        });

        var lines = draft.lines || [];
        if (!lines.length) return;

        ensureRowCount(lines.length);
        var rows = visibleLineRows();
        lines.forEach(function (line, i) {
            var row = rows[i];
            if (!row) return;
            setProductCode(row, line.product_code, line.product_name);
            var qtyEl = row.querySelector('.jp-so-qty-total, input[name$="-qty"]');
            if (qtyEl && line.qty != null && line.qty !== '') qtyEl.value = line.qty;
            var sizeMap = line.size_qtys && typeof line.size_qtys === 'object' ? line.size_qtys : {};
            if (typeof window.jpSoWriteLineSizeQtys === 'function') {
                window.jpSoWriteLineSizeQtys(row, sizeMap);
            } else {
                var hidden = row.querySelector('.jp-so-size-qtys-json, input[name$="-size_qtys"]');
                if (hidden) hidden.value = JSON.stringify(sizeMap);
            }
        });
    }

    var saveTimer = null;
    function scheduleSave() {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, SAVE_INTERVAL);
    }

    form.addEventListener('input', scheduleSave);
    form.addEventListener('change', scheduleSave);

    form.addEventListener('submit', function () {
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    });

    function initRestore() {
        var draft = loadDraft();
        if (!draft || !hasMeaningfulContent(draft)) return;
        // Chờ TomSelect + hydrate size xong
        setTimeout(function () {
            if (!formIsEmpty()) return;
            restoreDraft(draft);
        }, 400);
    }

    initRestore();
})();
