/**
 * Overlay loading khi gửi báo cáo (VP ngày/tuần, SX).
 * Submit qua fetch — thất bại mạng/server thì hiện overlay yêu cầu kiểm tra mạng.
 */
(function () {
    'use strict';

    var overlay = document.getElementById('jp-report-submit-loading');
    if (!overlay) return;

    var msgEl = overlay.querySelector('[data-loading-message]');
    var errorOverlay = document.getElementById('jp-report-submit-error');
    var errorCloseBtn = document.getElementById('jpReportSubmitErrorCloseBtn');
    var submitting = false;

    function syncCkEditor() {
        if (!window.CKEDITOR || !CKEDITOR.instances) return;
        Object.keys(CKEDITOR.instances).forEach(function (name) {
            if (Object.prototype.hasOwnProperty.call(CKEDITOR.instances, name)) {
                CKEDITOR.instances[name].updateElement();
            }
        });
    }

    function show(message) {
        hideError();
        if (msgEl && message) {
            msgEl.textContent = message;
        }
        overlay.hidden = false;
        overlay.setAttribute('aria-busy', 'true');
        document.body.classList.add('jp-report-submitting');
    }

    function hide() {
        overlay.hidden = true;
        overlay.setAttribute('aria-busy', 'false');
        document.body.classList.remove('jp-report-submitting');
    }

    function showErrorModal() {
        hide();
        if (!errorOverlay) {
            window.alert('Gửi báo cáo thất bại. Vui lòng kiểm tra kết nối mạng rồi gửi lại.');
            return;
        }
        errorOverlay.hidden = false;
        document.body.classList.add('jp-report-submit-error-open');
        if (errorCloseBtn) {
            window.setTimeout(function () {
                errorCloseBtn.focus();
            }, 50);
        }
    }

    function hideError() {
        if (!errorOverlay) return;
        errorOverlay.hidden = true;
        document.body.classList.remove('jp-report-submit-error-open');
    }

    function disableSubmitControls(form) {
        if (!form) return;
        form.querySelectorAll('button[type="submit"], input[type="submit"], .js-prod-submit-trigger, #prodSubmitConfirmBtn').forEach(function (btn) {
            btn.disabled = true;
        });
    }

    function enableSubmitControls(form) {
        if (!form) return;
        form.querySelectorAll('button[type="submit"], input[type="submit"], .js-prod-submit-trigger, #prodSubmitConfirmBtn').forEach(function (btn) {
            btn.disabled = false;
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

    function buildFormData(form, submitter) {
        var fd;
        try {
            fd = submitter ? new FormData(form, submitter) : new FormData(form);
        } catch (err) {
            fd = new FormData(form);
            if (submitter && submitter.name) {
                fd.append(submitter.name, submitter.value);
            }
        }
        if (!fd.get('action')) {
            var hiddenAction = form.querySelector('input[name="action"]');
            if (hiddenAction && hiddenAction.value) {
                fd.set('action', hiddenAction.value);
            } else {
                fd.set('action', 'submit');
            }
        }
        return fd;
    }

    function submitForm(form, submitter) {
        if (!form || submitting) return;
        submitting = true;
        syncCkEditor();
        show('Đang gửi báo cáo...');
        disableSubmitControls(form);

        var fd = buildFormData(form, submitter || null);
        var url = form.getAttribute('action') || window.location.href;
        var method = (form.getAttribute('method') || 'POST').toUpperCase();

        fetch(url, {
            method: method,
            body: fd,
            credentials: 'same-origin',
            redirect: 'follow',
            headers: {
                'X-Requested-With': 'XMLHttpRequest',
            },
        }).then(function (resp) {
            if (!resp.ok) {
                throw new Error('HTTP ' + resp.status);
            }
            window.location.href = resp.url || url;
        }).catch(function () {
            submitting = false;
            enableSubmitControls(form);
            showErrorModal();
        });
    }

    function armForm(form) {
        if (!form || form.dataset.jpSubmitArmed === '1') return;
        form.dataset.jpSubmitArmed = '1';
        form.addEventListener('submit', function (ev) {
            if (!isReportSubmit(ev.submitter, form)) return;
            ev.preventDefault();
            submitForm(form, ev.submitter);
        });
    }

    if (errorCloseBtn) {
        errorCloseBtn.addEventListener('click', hideError);
    }
    if (errorOverlay) {
        errorOverlay.addEventListener('click', function (ev) {
            if (ev.target === errorOverlay) hideError();
        });
    }

    document.querySelectorAll('form.js-report-submit-form').forEach(armForm);

    window.JpReportSubmitLoading = {
        show: show,
        hide: hide,
        armForm: armForm,
        syncCkEditor: syncCkEditor,
        disableSubmitControls: disableSubmitControls,
        enableSubmitControls: enableSubmitControls,
        submitForm: submitForm,
        showErrorModal: showErrorModal,
        hideError: hideError,
    };
})();
