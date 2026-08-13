/**
 * Auto-save form lên đơn đặt hàng (san-xuat/don-hang/them) vào localStorage.
 * Reload trang khôi phục bản nháp (< 7 ngày). Xóa draft sau khi tạo đơn thành công.
 */
(function () {
    'use strict';

    var form = document.getElementById('jp-so-form');
    if (!form) return;

    var STORAGE_KEY = 'sx_sales_order_draft';
    var PENDING_KEY = 'sx_sales_order_draft_pending';
    var SAVE_INTERVAL = 400;
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

    function parseJson(raw, fallback) {
        if (!raw) return fallback;
        try {
            var parsed = JSON.parse(raw);
            return parsed == null ? fallback : parsed;
        } catch (e) {
            return fallback;
        }
    }

    function collectLines() {
        syncAllSizeJson();
        var lines = [];
        visibleLineRows().forEach(function (row) {
            var codeEl = row.querySelector('.jp-sx-product-code-select, select[name$="-product_code"]');
            var nameEl = row.querySelector('input[name$="-product_name"]');
            var qtyEl = row.querySelector('.jp-so-qty-total, input[name$="-qty"]');
            var sizeEl = row.querySelector('.jp-so-size-qtys-json, input[name$="-size_qtys"]');
            var bomEl = row.querySelector('.jp-so-bom-select, select[name$="-bom_version_id"]');
            var rtEl = row.querySelector('.jp-so-routing-select, select[name$="-routing_id"]');
            var smvEl = row.querySelector('.jp-so-smv-json, input[name$="-applied_smv_json"]');
            var code = codeEl ? (codeEl.value || '').trim() : '';
            var name = nameEl ? (nameEl.value || '').trim() : '';
            var qty = qtyEl ? (qtyEl.value || '').trim() : '';
            var bomId = bomEl ? (bomEl.value || '').trim() : '';
            var routingId = rtEl ? (rtEl.value || '').trim() : '';
            if (bomId === '__create__') bomId = '';
            if (routingId === '__create__') routingId = '';
            var sizeQtys = parseJson(sizeEl ? sizeEl.value : '', {});
            if (!sizeQtys || typeof sizeQtys !== 'object' || Array.isArray(sizeQtys)) sizeQtys = {};
            var appliedSmv = parseJson(smvEl ? smvEl.value : '', []);
            if (!Array.isArray(appliedSmv)) appliedSmv = [];
            if (
                !code && !name && (!qty || qty === '0')
                && !Object.keys(sizeQtys).length && !bomId && !routingId && !appliedSmv.length
            ) return;
            lines.push({
                product_code: code,
                product_name: name,
                qty: qty,
                size_qtys: sizeQtys,
                bom_version_id: bomId,
                routing_id: routingId,
                applied_smv: appliedSmv,
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

    function lineHasContent(line) {
        if (!line) return false;
        if ((line.product_code || '').trim()) return true;
        if ((line.product_name || '').trim()) return true;
        if ((line.qty || '').trim() && line.qty !== '0') return true;
        if ((line.bom_version_id || '').trim()) return true;
        if ((line.routing_id || '').trim()) return true;
        if (line.applied_smv && line.applied_smv.length) return true;
        if (line.size_qtys && typeof line.size_qtys === 'object') {
            var keys = Object.keys(line.size_qtys);
            for (var j = 0; j < keys.length; j++) {
                if (Number(line.size_qtys[keys[j]]) > 0) return true;
            }
        }
        return false;
    }

    function hasMeaningfulContent(draft) {
        if (!draft) return false;
        var h = draft.header || {};
        if ((h.code || '').trim()) return true;
        if ((h.customer_name || '').trim()) return true;
        if ((h.notes || '').trim()) return true;
        var lines = draft.lines || [];
        for (var i = 0; i < lines.length; i++) {
            if (lineHasContent(lines[i])) return true;
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
            if (h[name] == null || h[name] === '') return;
            if (name === 'customer_name' && el.tomselect) {
                var val = String(h[name]);
                if (!el.tomselect.options[val]) {
                    el.tomselect.addOption({ id: val, text: val, name: val, code: '', phone: '' });
                }
                el.tomselect.setValue(val, true);
                return;
            }
            el.value = h[name];
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
            var smvEl = row.querySelector('.jp-so-smv-json, input[name$="-applied_smv_json"]');
            if (smvEl && line.applied_smv != null) {
                smvEl.value = typeof line.applied_smv === 'string'
                    ? line.applied_smv
                    : JSON.stringify(line.applied_smv || []);
            }
            if (typeof window.jpSoLoadLineVersions === 'function') {
                window.jpSoLoadLineVersions(
                    row,
                    line.bom_version_id || '',
                    line.routing_id || '',
                    true
                );
            }
        });
    }

    var saveTimer = null;
    function scheduleSave() {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, SAVE_INTERVAL);
    }

    window.jpSoAfterLineVersions = scheduleSave;

    form.addEventListener('input', scheduleSave);
    form.addEventListener('change', scheduleSave);
    document.addEventListener('jp-so-product-changed', scheduleSave);

    form.addEventListener('submit', function () {
        saveDraft();
        try { sessionStorage.setItem(PENDING_KEY, '1'); } catch (e) {}
    });

    window.addEventListener('pagehide', saveDraft);
    window.addEventListener('beforeunload', saveDraft);

    function initRestore() {
        var pending = false;
        try { pending = sessionStorage.getItem(PENDING_KEY) === '1'; } catch (e) {}
        if (pending) {
            try { sessionStorage.removeItem(PENDING_KEY); } catch (e) {}
            if (!formIsEmpty()) {
                saveDraft();
                return;
            }
            try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
            return;
        }

        var draft = loadDraft();
        if (!draft || !hasMeaningfulContent(draft)) return;
        if (!formIsEmpty()) return;
        restoreDraft(draft);
    }

    initRestore();
})();
