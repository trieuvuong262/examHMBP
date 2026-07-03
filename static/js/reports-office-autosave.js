/**
 * Auto-save báo cáo VP đang nhập dở vào localStorage.
 * Khi load lại trang, nếu form chưa có nội dung (report mới) thì restore.
 * Xóa draft khi submit thành công.
 */
(function () {
    'use strict';

    var form = document.getElementById('office-report-form');
    if (!form) return;
    if (form.dataset.reportLocked) return; // Không auto-save khi đã khóa

    var periodInput = form.querySelector('input[name="period"]');
    var dateInput = form.querySelector('[name="report_date"]') || form.querySelector('[name="month"]');
    if (!periodInput || !dateInput) return;

    var period = periodInput.value || 'day';
    var dateVal = dateInput.value || 'unknown';
    var STORAGE_KEY = 'vp_draft_' + period + '_' + dateVal;
    var SAVE_INTERVAL = 3000; // ms

    var titleEl = document.getElementById('id_title');
    var linksEl = document.getElementById('id_links');
    var sheetEl = document.getElementById('id_spreadsheet_data');

    function getCkContent() {
        // CKEditor 4 instance
        if (window.CKEDITOR && CKEDITOR.instances) {
            for (var name in CKEDITOR.instances) {
                if (CKEDITOR.instances.hasOwnProperty(name)) {
                    return CKEDITOR.instances[name].getData();
                }
            }
        }
        // Fallback: textarea
        var ta = document.getElementById('id_document_html');
        return ta ? ta.value : '';
    }

    function setCkContent(html) {
        if (window.CKEDITOR && CKEDITOR.instances) {
            for (var name in CKEDITOR.instances) {
                if (CKEDITOR.instances.hasOwnProperty(name)) {
                    CKEDITOR.instances[name].setData(html);
                    return;
                }
            }
        }
        var ta = document.getElementById('id_document_html');
        if (ta) ta.value = html;
    }

    function collectDraft() {
        return {
            title: titleEl ? titleEl.value : '',
            links: linksEl ? linksEl.value : '',
            sheet: sheetEl ? sheetEl.value : '',
            document_html: getCkContent(),
            ts: Date.now(),
        };
    }

    function hasMeaningfulContent(draft) {
        if (draft.title && draft.title.trim()) return true;
        if (draft.links && draft.links.trim()) return true;
        if (draft.document_html && draft.document_html.replace(/<[^>]*>/g, '').trim()) return true;
        if (draft.sheet) {
            try {
                var s = JSON.parse(draft.sheet);
                if (s && s.rows) {
                    for (var i = 0; i < s.rows.length; i++) {
                        for (var j = 0; j < s.rows[i].length; j++) {
                            if (s.rows[i][j] && s.rows[i][j].trim()) return true;
                        }
                    }
                }
            } catch (e) {}
        }
        return false;
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
            // Chỉ restore nếu draft < 7 ngày
            if (draft.ts && (Date.now() - draft.ts) > 7 * 24 * 60 * 60 * 1000) {
                localStorage.removeItem(STORAGE_KEY);
                return null;
            }
            return draft;
        } catch (e) { return null; }
    }

    function formIsEmpty() {
        if (titleEl && titleEl.value.trim()) return false;
        if (linksEl && linksEl.value.trim()) return false;
        var ck = getCkContent();
        if (ck && ck.replace(/<[^>]*>/g, '').trim()) return false;
        if (sheetEl && sheetEl.value) {
            try {
                var s = JSON.parse(sheetEl.value);
                if (s && s.rows) {
                    for (var i = 0; i < s.rows.length; i++) {
                        for (var j = 0; j < s.rows[i].length; j++) {
                            if (s.rows[i][j] && s.rows[i][j].trim()) return false;
                        }
                    }
                }
            } catch (e) {}
        }
        return true;
    }

    function restoreDraft(draft) {
        if (titleEl && draft.title) titleEl.value = draft.title;
        if (linksEl && draft.links) linksEl.value = draft.links;
        if (sheetEl && draft.sheet) {
            sheetEl.value = draft.sheet;
            // Trigger re-render bảng
            sheetEl.dispatchEvent(new Event('change'));
        }
        if (draft.document_html) {
            // CKEditor có thể chưa ready, chờ
            function tryCk() {
                if (window.CKEDITOR && CKEDITOR.instances) {
                    for (var name in CKEDITOR.instances) {
                        if (CKEDITOR.instances.hasOwnProperty(name)) {
                            var ed = CKEDITOR.instances[name];
                            if (ed.status === 'ready') {
                                ed.setData(draft.document_html);
                            } else {
                                ed.on('instanceReady', function () { ed.setData(draft.document_html); });
                            }
                            return;
                        }
                    }
                }
                setTimeout(tryCk, 300);
            }
            tryCk();
        }
    }

    // Restore on load (chỉ khi form trống = báo cáo mới)
    function initRestore() {
        var draft = loadDraft();
        if (!draft || !hasMeaningfulContent(draft)) return;
        // Chờ CKEditor init xong rồi check form empty
        setTimeout(function () {
            if (formIsEmpty()) {
                restoreDraft(draft);
            }
        }, 800);
    }

    // Auto-save định kỳ
    var saveTimer = null;
    function scheduleSave() {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(saveDraft, SAVE_INTERVAL);
    }

    // Lắng nghe thay đổi
    form.addEventListener('input', scheduleSave);
    form.addEventListener('change', scheduleSave);
    // CKEditor changes
    function bindCkChange() {
        if (window.CKEDITOR && CKEDITOR.instances) {
            for (var name in CKEDITOR.instances) {
                if (CKEDITOR.instances.hasOwnProperty(name)) {
                    CKEDITOR.instances[name].on('change', scheduleSave);
                    return;
                }
            }
        }
        setTimeout(bindCkChange, 500);
    }
    bindCkChange();

    // Xóa draft khi submit thành công
    form.addEventListener('submit', function () {
        try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    });

    // Restore
    initRestore();
})();
