/**
 * Overlay loading khi gửi báo cáo (VP ngày/tuần, SX).
 */
(function () {
    'use strict';

    var overlay = document.getElementById('jp-report-submit-loading');
    if (!overlay) return;

    var msgEl = overlay.querySelector('[data-loading-message]');

    function syncCkEditor() {
        if (!window.CKEDITOR || !CKEDITOR.instances) return;
        Object.keys(CKEDITOR.instances).forEach(function (name) {
            if (Object.prototype.hasOwnProperty.call(CKEDITOR.instances, name)) {
                CKEDITOR.instances[name].updateElement();
            }
        });
    }

    function show(message) {
        if (msgEl && message) {
            msgEl.textContent = message;
        }
        overlay.hidden = false;
        overlay.setAttribute('aria-busy', 'true');
        document.body.classList.add('jp-report-submitting');
    }

    function disableSubmitControls(form) {
        if (!form) return;
        form.querySelectorAll('button[type="submit"], input[type="submit"]').forEach(function (btn) {
            btn.disabled = true;
        });
    }

    function isReportSubmit(submitter, form) {
        if (!form) return false;
        if (submitter && submitter.getAttribute('name') === 'action') {
            return (submitter.getAttribute('value') || submitter.value) === 'submit';
        }
        if (submitter && submitter.type === 'submit') {
            var hidden = form.querySelector('input[name="action"][value="submit"]');
            if (hidden) return true;
        }
        return false;
    }

    function armForm(form) {
        if (!form || form.dataset.jpSubmitArmed === '1') return;
        form.dataset.jpSubmitArmed = '1';
        form.addEventListener('submit', function (ev) {
            if (!isReportSubmit(ev.submitter, form)) return;
            syncCkEditor();
            show('Đang gửi báo cáo...');
            disableSubmitControls(form);
        });
    }

    document.querySelectorAll('form.js-report-submit-form').forEach(armForm);

    window.JpReportSubmitLoading = {
        show: show,
        armForm: armForm,
        syncCkEditor: syncCkEditor,
        disableSubmitControls: disableSubmitControls,
    };
})();
